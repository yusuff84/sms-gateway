import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from sqladmin import Admin
from sqladmin.authentication import login_required
from sqlalchemy import select, func, desc
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

from app.config import settings
from app.database import init_db, engine, AsyncSessionLocal
from app.seed import seed_initial_data
from app.auth.admin_auth import admin_auth
from app.core.timezone import now_msk, to_msk, format_time_msk
from app.models.sms_task import SmsTask, SmsStatus
from app.models.device import Device
from app.models.blacklisted_phone import BlacklistedPhone
from app.admin import (
    ApiKeyAdmin,
    DeviceAdmin,
    SmsTaskAdmin,
    SmsTemplateAdmin,
    BlacklistedPhoneAdmin,
    AbusersAnalyticsView
)
from app.api.v1 import api_v1_router
from app.ws.endpoint import router as ws_router
from app.ws.manager import manager
from app.core.limiter import limiter

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("sms_gateway")

# Prometheus metrics
SMS_PROCESSED_TOTAL = Counter('sms_processed_total', 'Total number of SMS tasks processed', ['status'])
ACTIVE_DEVICES_GAUGE = Gauge('sms_active_devices', 'Number of active connected Android devices')


class SMSGatewayAdmin(Admin):
    """Custom Admin with Modern Analytics Dashboard & Anti-Fraud Abusers Overview (Moscow Time MSK)."""
    @login_required
    async def index(self, request: Request) -> Response:
        cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
        # 00:00 MSK today converted to UTC for database queries
        now_in_msk = now_msk()
        today_start_msk = now_in_msk.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start_msk.astimezone(timezone.utc)

        async with AsyncSessionLocal() as session:
            # 1. Total tasks
            total_res = await session.execute(select(func.count(SmsTask.id)))
            total_tasks = total_res.scalar() or 0

            # 2. Today tasks (from 00:00 MSK)
            today_res = await session.execute(select(func.count(SmsTask.id)).where(SmsTask.created_at >= today_start_utc))
            tasks_today = today_res.scalar() or 0

            # 3. 7 days tasks
            seven_days_res = await session.execute(select(func.count(SmsTask.id)).where(SmsTask.created_at >= cutoff_7d))
            tasks_7d = seven_days_res.scalar() or 0

            # 4. Delivered tasks & rate
            delivered_res = await session.execute(select(func.count(SmsTask.id)).where(SmsTask.status == SmsStatus.DELIVERED))
            delivered_count = delivered_res.scalar() or 0
            delivery_rate = round((delivered_count / total_tasks * 100), 1) if total_tasks > 0 else 100.0

            # 5. Devices
            devices_res = await session.execute(select(Device).where(Device.is_active == True))
            devices = devices_res.scalars().all()
            online_devices = sum(1 for d in devices if d.is_online)

            # 6. Blocked count
            blocked_res = await session.execute(select(func.count(BlacklistedPhone.id)).where(BlacklistedPhone.is_active == True))
            blacklisted_count = blocked_res.scalar() or 0

            # 7. Top abusers in last 7 days (>= 2 requests)
            abusers_stmt = (
                select(
                    SmsTask.phone_number,
                    func.count(SmsTask.id).label('count_7d'),
                    func.max(SmsTask.created_at).label('last_seen')
                )
                .where(SmsTask.created_at >= cutoff_7d)
                .group_by(SmsTask.phone_number)
                .having(func.count(SmsTask.id) >= 2)
                .order_by(desc('count_7d'))
                .limit(5)
            )
            top_abusers_res = await session.execute(abusers_stmt)
            top_abusers = top_abusers_res.all()

            # Set of currently blocked phone numbers
            bl_res = await session.execute(select(BlacklistedPhone.phone_number).where(BlacklistedPhone.is_active == True))
            blocked_numbers = set(bl_res.scalars().all())

            # 8. Recent 7 tasks formatted in Moscow time (MSK)
            recent_res = await session.execute(select(SmsTask).order_by(SmsTask.created_at.desc()).limit(7))
            recent_tasks = recent_res.scalars().all()
            for t in recent_tasks:
                t.created_at_msk = format_time_msk(t.created_at)

            context = {
                "request": request,
                "total_tasks": total_tasks,
                "tasks_today": tasks_today,
                "tasks_7d": tasks_7d,
                "delivered_count": delivered_count,
                "delivery_rate": delivery_rate,
                "devices": devices,
                "online_devices": online_devices,
                "blacklisted_count": blacklisted_count,
                "top_abusers": top_abusers,
                "blocked_numbers": blocked_numbers,
                "recent_tasks": recent_tasks,
            }
            return await self.templates.TemplateResponse(request, "sqladmin/index.html", context)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting production SMS Gateway backend...")
    await init_db()
    await seed_initial_data()
    logger.info("Database initialized and ready for production traffic.")
    yield
    logger.info("Shutting down SMS Gateway backend...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-grade SMS Gateway backend for forwarding verification codes and SMS messages to Android devices.",
    version="1.1.0",
    lifespan=lifespan
)

# Register rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Starlette SessionMiddleware required by SQLAdmin
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=14 * 24 * 3600  # 14 days
)

# SQLAdmin Dashboard
admin = SMSGatewayAdmin(
    app=app,
    engine=engine,
    title="SMS Gateway Admin",
    authentication_backend=admin_auth,
    base_url="/admin",
    templates_dir="app/templates"
)
admin.add_view(ApiKeyAdmin)
admin.add_view(DeviceAdmin)
admin.add_view(SmsTemplateAdmin)
admin.add_view(BlacklistedPhoneAdmin)
admin.add_view(SmsTaskAdmin)
admin.add_base_view(AbusersAnalyticsView)

# Include API Routers
app.include_router(api_v1_router, prefix=settings.API_V1_STR)
app.include_router(ws_router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["Health & Monitoring"])
async def health():
    devices_count = len(manager.active_connections)
    ACTIVE_DEVICES_GAUGE.set(devices_count)
    return {
        "status": "ok",
        "active_devices_count": devices_count,
        "is_gateway_ready": manager.is_device_online(),
        "version": "1.1.0"
    }


@app.get("/metrics", tags=["Health & Monitoring"], include_in_schema=True)
async def prometheus_metrics():
    """Prometheus metrics endpoint for Grafana/Prometheus scraping."""
    ACTIVE_DEVICES_GAUGE.set(len(manager.active_connections))
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
