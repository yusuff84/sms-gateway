from datetime import datetime, timezone, timedelta
from typing import Optional
from markupsafe import Markup
from sqlalchemy import select, func, desc, case
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse
from sqladmin import ModelView, BaseView, expose

from app.database import AsyncSessionLocal
from app.core.timezone import to_msk, format_datetime_msk, format_time_msk
from app.models.api_key import ApiKey
from app.models.device import Device
from app.models.sms_task import SmsTask, SmsStatus
from app.models.sms_template import SmsTemplate
from app.models.blacklisted_phone import BlacklistedPhone


class BaseAdminModelView(ModelView):
    """Base admin model view formatting all datetimes in Moscow Time (MSK, UTC+3)."""
    column_type_formatters = {datetime: lambda v: format_datetime_msk(v)}
    column_type_formatters_detail = {datetime: lambda v: format_datetime_msk(v)}


def format_device_online_badge(model: Device, attribute: str) -> Markup:
    if model.is_online:
        return Markup(
            '<span class="badge py-1 px-3 d-inline-flex align-items-center" '
            'style="background: #f0fdfa; color: #0f766e; border: 1px solid #99f6e4; border-radius: 9999px;">'
            '<span class="status-dot status-dot-animated me-2" style="background: #0d9488;"></span>В сети</span>'
        )
    return Markup(
        '<span class="badge py-1 px-3 d-inline-flex align-items-center" '
        'style="background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; border-radius: 9999px;">'
        '<i class="fa-solid fa-circle text-muted me-1" style="font-size: 0.45rem;"></i>Офлайн</span>'
    )


def format_device_battery_badge(model: Device, attribute: str) -> Markup:
    if model.battery_level is None:
        return Markup('<span class="text-muted">—</span>')
    level = model.battery_level
    charging_icon = ' <i class="fa-solid fa-bolt ms-1" style="color: #0d9488;" title="На зарядке"></i>' if model.is_charging else ''

    if level >= 50:
        style = "background: #f0fdfa; color: #0f766e; border: 1px solid #99f6e4;"
        icon = '<i class="fa-solid fa-battery-full me-1" style="color: #0d9488;"></i>'
    elif level >= 20:
        style = "background: #fffbeb; color: #b45309; border: 1px solid #fde68a;"
        icon = '<i class="fa-solid fa-battery-half me-1 text-warning"></i>'
    else:
        style = "background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca;"
        icon = '<i class="fa-solid fa-battery-quarter me-1 text-danger"></i>'

    return Markup(f'<span class="badge py-1 px-3" style="{style} border-radius: 9999px;">{icon}{level}%{charging_icon}</span>')


def format_sms_status_badge(model: SmsTask, attribute: str) -> Markup:
    st = model.status
    if st == SmsStatus.DELIVERED:
        return Markup(
            '<span class="badge px-3 py-1" style="background: #f0fdfa; color: #0f766e; border: 1px solid #99f6e4; border-radius: 9999px;">'
            '<i class="fa-solid fa-circle-check me-1" style="color: #0d9488;"></i>DELIVERED</span>'
        )
    elif st == SmsStatus.SENT:
        return Markup(
            '<span class="badge px-3 py-1" style="background: #f8fafc; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 9999px;">'
            '<i class="fa-solid fa-paper-plane me-1 text-muted"></i>SENT</span>'
        )
    elif st == SmsStatus.SENDING or st == SmsStatus.QUEUED:
        return Markup(
            f'<span class="badge px-3 py-1" style="background: #fffbeb; color: #b45309; border: 1px solid #fde68a; border-radius: 9999px;">'
            f'<i class="fa-solid fa-clock me-1"></i>{st}</span>'
        )
    elif st == SmsStatus.EXPIRED:
        return Markup(
            f'<span class="badge px-3 py-1" style="background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; border-radius: 9999px;">'
            f'<i class="fa-solid fa-hourglass-end me-1"></i>EXPIRED</span>'
        )
    elif st == SmsStatus.FAILED:
        err = f' title="{model.error_message}"' if model.error_message else ''
        return Markup(
            f'<span class="badge px-3 py-1" style="background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; border-radius: 9999px;"{err}>'
            f'<i class="fa-solid fa-triangle-exclamation me-1"></i>FAILED</span>'
        )
    return Markup(f'<span class="badge px-3 py-1" style="border-radius: 9999px;">{st}</span>')


def format_task_device_badge(model: SmsTask, attribute: str) -> Markup:
    if model.device:
        return Markup(
            '<span class="badge px-3 py-1 d-inline-flex align-items-center" '
            'style="background: #f8fafc; color: #0f172a; border: 1px solid #e2e8f0; border-radius: 9999px;">'
            f'<i class="fa-solid fa-mobile-screen me-2" style="color: #0d9488;"></i>{model.device.name}</span>'
        )
    return Markup('<span class="text-muted">—</span>')


def format_task_phone_number(model: SmsTask, attribute: str) -> Markup:
    return Markup(f'<span class="fw-bold font-monospace text-dark">{model.phone_number}</span>')


def format_task_sim_slot(model: SmsTask, attribute: str) -> Markup:
    slot = model.sim_slot or 1
    return Markup(
        '<span class="badge px-3 py-1" style="background: #f0fdfa; color: #0f766e; border: 1px solid #ccfbf1; border-radius: 9999px;">'
        f'<i class="fa-solid fa-sim-card me-1" style="color: #0d9488;"></i>SIM {slot}</span>'
    )


class ApiKeyAdmin(BaseAdminModelView, model=ApiKey):
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


class DeviceAdmin(BaseAdminModelView, model=Device):
    name = "Android Устройство"
    name_plural = "Android Устройства (Пул)"
    icon = "fa-solid fa-mobile-screen-button"

    column_list = [
        Device.id,
        Device.name,
        Device.is_online,
        Device.battery_level,
        Device.total_sent_count,
        Device.token,
        Device.is_active,
        Device.last_ping_at,
    ]
    column_formatters = {
        Device.is_online: format_device_online_badge,
        Device.battery_level: format_device_battery_badge,
        Device.total_sent_count: lambda m, a: Markup(
            f'<span class="badge px-3 py-1 fw-bold fs-4" style="background: #f0fdfa; color: #0f766e; border: 1px solid #99f6e4; border-radius: 9999px;">{m.total_sent_count}</span>'
        ),
    }
    column_searchable_list = [Device.name, Device.token]
    column_sortable_list = [Device.id, Device.is_online, Device.total_sent_count, Device.last_ping_at]
    form_columns = [Device.name, Device.token, Device.sim_count, Device.max_hourly_per_sim, Device.is_active]


class SmsTemplateAdmin(BaseAdminModelView, model=SmsTemplate):
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


class BlacklistedPhoneAdmin(BaseAdminModelView, model=BlacklistedPhone):
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
    column_formatters = {
        BlacklistedPhone.is_active: lambda m, a: Markup(
            '<span class="badge px-3 py-1" style="background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; border-radius: 9999px;">'
            '<i class="fa-solid fa-ban me-1"></i>Заблокирован</span>'
        ) if m.is_active else Markup(
            '<span class="badge px-3 py-1" style="background: #f0fdfa; color: #0f766e; border: 1px solid #99f6e4; border-radius: 9999px;">'
            '<i class="fa-solid fa-check me-1"></i>Разблокирован</span>'
        )
    }
    column_searchable_list = [BlacklistedPhone.phone_number, BlacklistedPhone.reason]
    column_sortable_list = [BlacklistedPhone.id, BlacklistedPhone.created_at, BlacklistedPhone.is_active]
    form_columns = [BlacklistedPhone.phone_number, BlacklistedPhone.reason, BlacklistedPhone.is_active]


class SmsTaskAdmin(BaseAdminModelView, model=SmsTask):
    name = "SMS Сообщение"
    name_plural = "SMS Сообщения (Логи)"
    icon = "fa-solid fa-envelope"

    column_list = [
        SmsTask.id,
        SmsTask.phone_number,
        SmsTask.message,
        SmsTask.status,
        SmsTask.device,
        SmsTask.sim_slot,
        SmsTask.created_at,
        SmsTask.sent_at,
        SmsTask.delivered_at,
        SmsTask.error_message,
    ]
    column_formatters = {
        SmsTask.status: format_sms_status_badge,
        SmsTask.device: format_task_device_badge,
        SmsTask.phone_number: format_task_phone_number,
        SmsTask.sim_slot: format_task_sim_slot,
    }
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
                    "last_seen_msk": format_datetime_msk(r.last_seen, "%d.%m.%Y %H:%M"),
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
