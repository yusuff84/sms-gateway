import logging
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.api_key import ApiKey
from app.models.device import Device
from app.models.sms_template import SmsTemplate

logger = logging.getLogger("sms_gateway.seed")

DEFAULT_API_KEY = "sms_ak_demo_master_token_12345"
DEFAULT_DEVICE_TOKEN = "sms_dev_android_gateway_token_9999"

INITIAL_TEMPLATES = [
    {
        "name": "Стандартный проверочный код",
        "category": "auth",
        "template_text": "{Ваш |}код подтверждения: {code}. {Никому не сообщайте|Не сообщайте его никому|Срок действия 5 минут}."
    },
    {
        "name": "Код для входа",
        "category": "auth",
        "template_text": "{Код для входа|Проверочный код}: {code}. {Никому не сообщайте|Действует 5 минут}."
    },
    {
        "name": "Авторизация в аккаунте",
        "category": "auth",
        "template_text": "{Вход в аккаунт|Авторизация}. {Ваш проверочный код|Код}: {code}. {Никому не передавайте|Действителен 5 мин}."
    },
    {
        "name": "Формат код-тире",
        "category": "auth",
        "template_text": "{code} — {ваш |}код для входа. {Никому не сообщайте его|Не передавайте третьим лицам}."
    },
    {
        "name": "Вежливый деловой стиль",
        "category": "auth",
        "template_text": "{Здравствуйте! |}Код подтверждения: {code}. {Никому не сообщайте|Срок действия 5 минут}."
    },
    {
        "name": "Подтверждение действия",
        "category": "action",
        "template_text": "{Подтверждение операции|Код подтверждения}: {code}. {Срок действия 5 мин|Никому не сообщайте}."
    },
    {
        "name": "Восстановление доступа",
        "category": "recovery",
        "template_text": "{Сброс пароля|Восстановление доступа}. Код: {code}. {Никому не сообщайте|Если не запрашивали, смените пароль}."
    }
]


async def seed_initial_data():
    try:
        async with AsyncSessionLocal() as session:
            # Check ApiKeys
            res = await session.execute(select(ApiKey).where(ApiKey.key == DEFAULT_API_KEY))
            existing_key = res.first()
            if not existing_key:
                initial_key = ApiKey(
                    key=DEFAULT_API_KEY,
                    name="Default Service Key",
                    description="Initial master API token for sending SMS"
                )
                session.add(initial_key)
                logger.info(f"Initialized default API Key: {DEFAULT_API_KEY}")

            # Check Devices
            res = await session.execute(select(Device).where(Device.token == DEFAULT_DEVICE_TOKEN))
            existing_device = res.first()
            if not existing_device:
                initial_device = Device(
                    token=DEFAULT_DEVICE_TOKEN,
                    name="Primary Android Phone",
                    sim_count=1,
                    last_sim_slot=1,
                    is_active=True,
                    is_online=False
                )
                session.add(initial_device)
                logger.info(f"Initialized default Device Token: {DEFAULT_DEVICE_TOKEN}")

            # Check Templates
            res_t = await session.execute(select(SmsTemplate))
            existing_template = res_t.first()
            if not existing_template:
                for item in INITIAL_TEMPLATES:
                    tmpl = SmsTemplate(
                        name=item["name"],
                        category=item["category"],
                        template_text=item["template_text"],
                        is_active=True,
                        usage_count=0
                    )
                    session.add(tmpl)
                logger.info(f"Initialized {len(INITIAL_TEMPLATES)} anti-fraud SMS templates.")

            await session.commit()
    except Exception as e:
        logger.debug(f"Seed data already initialized or concurrent init: {e}")
