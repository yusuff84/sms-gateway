from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import select, func, desc, case
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse
from sqladmin import ModelView, BaseView, expose

from app.database import AsyncSessionLocal
from app.models.api_key import ApiKey
from app.models.device import Device
from app.models.sms_task import SmsTask
from app.models.sms_template import SmsTemplate
from app.models.blacklisted_phone import BlacklistedPhone


class ApiKeyAdmin(ModelView, model=ApiKey):
    name = "API Ключ"
    name_plural = "API Ключи"
    icon = "fa-solid fa-key"

    column_list = [
        ApiKey.id,
        ApiKey.name,
        ApiKey.key,
        ApiKey.is_active,
        ApiKey.created_at,
        ApiKey.last_used_at,
    ]
    column_searchable_list = [ApiKey.name, ApiKey.key]
    column_sortable_list = [ApiKey.id, ApiKey.created_at, ApiKey.last_used_at]
    form_columns = [ApiKey.name, ApiKey.description, ApiKey.is_active]


class DeviceAdmin(ModelView, model=Device):
    name = "Android Устройство"
    name_plural = "Android Устройства"
    icon = "fa-solid fa-mobile-screen"

    column_list = [
        Device.id,
        Device.name,
        Device.token,
        Device.is_active,
        Device.is_online,
        Device.last_sim_slot,
        Device.total_sent_count,
        Device.battery_level,
        Device.is_charging,
        Device.last_ping_at,
    ]
    column_searchable_list = [Device.name, Device.token]
    column_sortable_list = [Device.id, Device.is_online, Device.total_sent_count, Device.last_ping_at]
    form_columns = [Device.name, Device.token, Device.sim_count, Device.max_hourly_per_sim, Device.is_active]


class SmsTemplateAdmin(ModelView, model=SmsTemplate):
    name = "SMS Шаблон"
    name_plural = "SMS Шаблоны (Антифрод)"
    icon = "fa-solid fa-wand-magic-sparkles"

    column_list = [
        SmsTemplate.id,
        SmsTemplate.name,
        SmsTemplate.category,
        SmsTemplate.template_text,
        SmsTemplate.usage_count,
        SmsTemplate.is_active,
        SmsTemplate.created_at,
    ]
    column_searchable_list = [SmsTemplate.name, SmsTemplate.template_text, SmsTemplate.category]
    column_sortable_list = [SmsTemplate.id, SmsTemplate.usage_count, SmsTemplate.created_at]
    form_columns = [SmsTemplate.name, SmsTemplate.category, SmsTemplate.template_text, SmsTemplate.is_active]


class BlacklistedPhoneAdmin(ModelView, model=BlacklistedPhone):
    name = "Черный список"
    name_plural = "Черный список (Блокировки)"
    icon = "fa-solid fa-ban"

    column_list = [
        BlacklistedPhone.id,
        BlacklistedPhone.phone_number,
        BlacklistedPhone.reason,
        BlacklistedPhone.is_active,
        BlacklistedPhone.created_at,
        BlacklistedPhone.updated_at,
    ]
    column_searchable_list = [BlacklistedPhone.phone_number, BlacklistedPhone.reason]
    column_sortable_list = [BlacklistedPhone.id, BlacklistedPhone.created_at, BlacklistedPhone.is_active]
    form_columns = [BlacklistedPhone.phone_number, BlacklistedPhone.reason, BlacklistedPhone.is_active]


class SmsTaskAdmin(ModelView, model=SmsTask):
    name = "SMS Сообщение"
    name_plural = "SMS Сообщения"
    icon = "fa-solid fa-envelope"

    column_list = [
        SmsTask.id,
        SmsTask.phone_number,
        SmsTask.message,
        SmsTask.status,
        SmsTask.sim_slot,
        SmsTask.created_at,
        SmsTask.expires_at,
        SmsTask.sent_at,
        SmsTask.error_message,
    ]
    column_searchable_list = [SmsTask.phone_number, SmsTask.message, SmsTask.id, SmsTask.status]
    column_sortable_list = [SmsTask.created_at, SmsTask.status, SmsTask.sim_slot]
    column_default_sort = ("created_at", True)  # Descending by default
    can_create = False  # SMS should be sent via API


class AbusersAnalyticsView(BaseView):
    name = "Абузеры (Аналитика 7 дней)"
    icon = "fa-solid fa-user-shield"

    @expose("/abusers", methods=["GET"])
    async def list_abusers(self, request: Request) -> Response:
        filter_mode = request.query_params.get("filter", "abusers")  # default to >= 2 requests
        search_query = request.query_params.get("q", "").strip()

        cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)
        cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)

        async with AsyncSessionLocal() as session:
            # Query grouped tasks
            base_stmt = (
                select(
                    SmsTask.phone_number,
                    func.count(SmsTask.id).label('count_total'),
                    func.sum(case((SmsTask.created_at >= cutoff_7d, 1), else_=0)).label('count_7d'),
                    func.sum(case((SmsTask.created_at >= cutoff_24h, 1), else_=0)).label('count_24h'),
                    func.max(SmsTask.created_at).label('last_seen')
                )
                .group_by(SmsTask.phone_number)
            )

            if search_query:
                base_stmt = base_stmt.where(SmsTask.phone_number.like(f"%{search_query}%"))

            if filter_mode == "abusers":
                base_stmt = base_stmt.having(func.sum(case((SmsTask.created_at >= cutoff_7d, 1), else_=0)) >= 2)
            elif filter_mode == "critical":
                base_stmt = base_stmt.having(func.sum(case((SmsTask.created_at >= cutoff_7d, 1), else_=0)) >= 8)
            else:
                base_stmt = base_stmt.having(func.sum(case((SmsTask.created_at >= cutoff_7d, 1), else_=0)) >= 1)

            base_stmt = base_stmt.order_by(desc('count_7d'))
            rows_res = await session.execute(base_stmt)
            raw_rows = rows_res.all()

            # Fetch blacklist state
            bl_res = await session.execute(select(BlacklistedPhone))
            blacklisted_map = {bl.phone_number: bl for bl in bl_res.scalars().all()}

            items = []
            for r in raw_rows:
                is_blocked = blacklisted_map.get(r.phone_number) is not None and blacklisted_map[r.phone_number].is_active
                block_reason = blacklisted_map[r.phone_number].reason if (is_blocked and r.phone_number in blacklisted_map) else None

                if filter_mode == "blocked" and not is_blocked:
                    continue

                risk = "normal"
                count_7d = r.count_7d or 0
                if count_7d >= 8:
                    risk = "critical"
                elif count_7d >= 4:
                    risk = "suspicious"
                elif count_7d >= 2:
                    risk = "repeat"

                items.append({
                    "phone_number": r.phone_number,
                    "count_7d": count_7d,
                    "count_24h": r.count_24h or 0,
                    "count_total": r.count_total or 0,
                    "last_seen": r.last_seen,
                    "risk": risk,
                    "is_blocked": is_blocked,
                    "block_reason": block_reason
                })

            context = {
                "request": request,
                "items": items,
                "filter_mode": filter_mode,
                "search_query": search_query,
                "total_count": len(items)
            }
            return await self.templates.TemplateResponse(request, "sqladmin/abusers.html", context)

    @expose("/abusers/block", methods=["POST"])
    async def block_number(self, request: Request) -> Response:
        form = await request.form()
        phone = str(form.get("phone_number", "")).strip()
        reason = str(form.get("reason", "Подозрительно высокая частота запросов кодов за неделю")).strip()
        if phone:
            async with AsyncSessionLocal() as session:
                st = select(BlacklistedPhone).where(BlacklistedPhone.phone_number == phone)
                res = await session.execute(st)
                existing = res.scalar_one_or_none()
                if existing:
                    existing.is_active = True
                    existing.reason = reason
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    new_bl = BlacklistedPhone(
                        phone_number=phone,
                        reason=reason,
                        is_active=True
                    )
                    session.add(new_bl)
                await session.commit()
        return RedirectResponse(request.headers.get("referer", "/admin/abusers"), status_code=303)

    @expose("/abusers/unblock", methods=["POST"])
    async def unblock_number(self, request: Request) -> Response:
        form = await request.form()
        phone = str(form.get("phone_number", "")).strip()
        if phone:
            async with AsyncSessionLocal() as session:
                st = select(BlacklistedPhone).where(BlacklistedPhone.phone_number == phone)
                res = await session.execute(st)
                existing = res.scalar_one_or_none()
                if existing:
                    existing.is_active = False
                    existing.updated_at = datetime.now(timezone.utc)
                    await session.commit()
        return RedirectResponse(request.headers.get("referer", "/admin/abusers"), status_code=303)
