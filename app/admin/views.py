from sqladmin import ModelView
from app.models.api_key import ApiKey
from app.models.device import Device
from app.models.sms_task import SmsTask
from app.models.sms_template import SmsTemplate


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
