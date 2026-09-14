import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse, Response
from sqladmin import Admin
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

from app.config import settings
from app.database import init_db, engine
from app.seed import seed_initial_data
from app.auth.admin_auth import admin_auth
from app.admin.views import ApiKeyAdmin, DeviceAdmin, SmsTaskAdmin, SmsTemplateAdmin
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
admin = Admin(
    app=app,
    engine=engine,
    title="SMS Gateway Admin",
    authentication_backend=admin_auth,
    base_url="/admin"
)
admin.add_view(ApiKeyAdmin)
admin.add_view(DeviceAdmin)
admin.add_view(SmsTemplateAdmin)
admin.add_view(SmsTaskAdmin)

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
