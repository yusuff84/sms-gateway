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
    # --- Категория AUTH (20 разнообразных шаблонов для кодов) ---
    {
        "name": "Стандартный код подтверждения",
        "category": "auth",
        "template_text": "{Ваш |}{код подтверждения|проверочный код}: {code}. {Никому не сообщайте|Не сообщайте его никому|Срок действия 5 минут}."
    },
    {
        "name": "Код для входа",
        "category": "auth",
        "template_text": "{Код для входа|Пароль для входа|Проверочный код}: {code}. {Никому не говорите|Действует 5 минут}."
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
        "name": "Предупреждение о безопасности",
        "category": "auth",
        "template_text": "Никому не говорите код: {code}. {Действителен 5 минут|Используется для авторизации}."
    },
    {
        "name": "Доступ в профиль",
        "category": "auth",
        "template_text": "{Для доступа в профиль используйте|Одноразовый} код: {code}. {Не сообщайте код никому|Действует 5 мин}."
    },
    {
        "name": "Запрос на авторизацию",
        "category": "auth",
        "template_text": "Запрос на авторизацию. {Код|Пароль}: {code}. {Никому не сообщайте|Если не запрашивали, проигнорируйте}."
    },
    {
        "name": "Короткий строгий формат",
        "category": "auth",
        "template_text": "{code} — проверочный код. Никому не сообщайте."
    },
    {
        "name": "Авторизация в системе",
        "category": "auth",
        "template_text": "{Вход в систему|Авторизация на сайте}. Код: {code}. {Срок действия 5 минут|Конфиденциально}."
    },
    {
        "name": "Одноразовый код",
        "category": "auth",
        "template_text": "{Ваш |}одноразовый код: {code}. {Никому не передавайте|Не сообщайте посторонним}."
    },
    {
        "name": "Проверка безопасности",
        "category": "auth",
        "template_text": "{Код безопасности|Проверка безопасности}: {code}. {Не сообщайте никому|Действителен 5 минут}."
    },
    {
        "name": "Подтверждение номера",
        "category": "auth",
        "template_text": "Для подтверждения номера введите код: {code}. {Никому не сообщайте|Действует 5 мин}."
    },
    {
        "name": "Код доступа к сервису",
        "category": "auth",
        "template_text": "Код доступа: {code}. {Не сообщайте его третьим лицам|Срок действия 5 минут}."
    },
    {
        "name": "Одноразовый пароль",
        "category": "auth",
        "template_text": "{code} — ваш одноразовый пароль для авторизации."
    },
    {
        "name": "Регистрация и подтверждение",
        "category": "auth",
        "template_text": "Код подтверждения регистрации: {code}. {Никому не сообщайте|Действителен 10 минут}."
    },
    {
        "name": "Защитный код",
        "category": "auth",
        "template_text": "{Ваш защитный код|Защитный код}: {code}. {Конфиденциально|Никому не говорите}."
    },
    {
        "name": "Личный кабинет",
        "category": "auth",
        "template_text": "Вход в личный кабинет. Код: {code}. {Не сообщайте его никому|Срок действия 5 мин}."
    },
    {
        "name": "Подтверждение входа",
        "category": "auth",
        "template_text": "Подтвердите вход. Код: {code}. {Никому не сообщайте|Действует 5 минут}."
    },
    {
        "name": "Лаконичный код-тире",
        "category": "auth",
        "template_text": "{code} — код подтверждения. {Никому не говорите|Не передавайте код}."
    },

    # --- Категория ACTION (подтверждение операций) ---
    {
        "name": "Подтверждение операции",
        "category": "action",
        "template_text": "{Подтверждение операции|Код подтверждения}: {code}. {Срок действия 5 мин|Никому не сообщайте}."
    },
    {
        "name": "Подтверждение действия",
        "category": "action",
        "template_text": "Подтвердите действие кодом: {code}. {Никому не сообщайте|Действителен 5 минут}."
    },
    {
        "name": "Одноразовый код операции",
        "category": "action",
        "template_text": "{Код для подтверждения операции|Одноразовый код}: {code}. {Не сообщайте посторонним|Срок 5 мин}."
    },

    # --- Категория RECOVERY (сброс пароля / восстановление) ---
    {
        "name": "Сброс пароля",
        "category": "recovery",
        "template_text": "{Сброс пароля|Восстановление доступа}. Код: {code}. {Никому не сообщайте|Если не запрашивали, смените пароль}."
    },
    {
        "name": "Восстановление доступа",
        "category": "recovery",
        "template_text": "Код для восстановления доступа: {code}. {Не сообщайте никому|Действует 5 минут}."
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
            existing_templates = res_t.scalars().all()
            if not existing_templates:
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
