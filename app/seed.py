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
        "name": "Стандартная верификация с вариациями",
        "category": "auth",
        "template_text": "{Ваш|Твой|Одноразовый} {код подтверждения|пароль для входа|проверочный код}: {code}. {Никому не сообщайте|Действителен 5 минут|Не передавайте третьим лицам}."
    },
    {
        "name": "Краткий стиль безопасности",
        "category": "auth",
        "template_text": "{Код|Пароль|Вход}: {code}. {Никому не говорите|Не передавайте никому|Конфиденциально}."
    },
    {
        "name": "Деловой стиль входа",
        "category": "auth",
        "template_text": "{Здравствуйте! |}{Для доступа в личный кабинет используйте|Код авторизации}: {code}. {Никому не сообщайте этот пароль|Безопасный вход}."
    },
    {
        "name": "Предупреждающий анти-фишинг",
        "category": "auth",
        "template_text": "{Внимание! |}{Код безопасности для входа в аккаунт|Запрос на авторизацию}: {code}. {Если это были не вы, проигнорируйте|Никогда не сообщайте код сотрудникам}."
    },
    {
        "name": "Завершение регистрации",
        "category": "auth",
        "template_text": "{Добро пожаловать! |}{Код для завершения регистрации|Подтверждение номера телефона}: {code}. {Код действует 10 минут|Безопасный код}."
    },
    {
        "name": "Подтверждение операции / действия",
        "category": "action",
        "template_text": "{Подтверждение действия|Код подтверждения операции}: {code}. {Срок действия 5 мин|Не сообщайте посторонним}."
    },
    {
        "name": "Сброс / восстановление доступа",
        "category": "recovery",
        "template_text": "{Восстановление доступа|Код сброса пароля}: {code}. {Никому не сообщайте|Если не запрашивали, смените пароль}."
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
