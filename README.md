# SMS Gateway (Backend API & WebSocket Server)

Боевой production-ready бэкенд на **Python (FastAPI)** для отправки SMS и кодов верификации через подключенный Android-смартфон в качестве GSM-шлюза.

📱 **Android-клиент шлюза**: [https://github.com/yusuff84/sms-gateway-android](https://github.com/yusuff84/sms-gateway-android)

---

## 🏛 Архитектура системы

```
+---------------------+           REST API (X-API-Key / Bearer)
|   Внешний сервис    | --------------------------------------------> [ FastAPI Backend ]
| (авторизация/коды)  | <-------------------------------------------       |
+---------------------+        Webhook Callback (SENT/DELIVERED)          |
                                                                   WebSocket (Realtime)
                                                                   + Очередь & TTL Expiration
                                                                   + Ротация SIM 1 ⇄ SIM 2
                                                                           |
                                                                           v
                                                                [ Android GSM Gateway ]
                                                                - Foreground Service 24/7
                                                                - Material 3 Design
                                                                - SmsManager (SIM карты)
                                                                           |
                                                                           v
                                                                    [ Абонент / GSM ]
```

---

## 🛡 Возможности и защита от блокировок (Production-Ready)

1. **Антифрод-система и Spintax рандомизация**:
   - Защита от блокировки SIM-карт спам-фильтрами сотовых операторов (МТС, Мегафон, Билайн, Tele2).
   - Поддержка вложенного Spintax: `{Ваш|Твой|Одноразовый} {код|пароль} для входа: {code}. {Никому не сообщайте|Действителен 5 минут}.`
   - Автоматическая вставка микро-энтропии (случайные ID и суффиксы сессий), исключающая совпадение хэшей сообщений в DPI оператора.
   - Возможность передать только `"code": "1234"` — сервер автоматически выберет наименее используемый шаблон из нужной категории (`auth`, `action`, `recovery`).
   - Управление шаблонами и просмотр статистики использования в веб-панели `/admin`.

2. **Идемпотентность (`idempotency_key`)**:
   - Предотвращение дублирования отправки SMS при повторных HTTP-запросах или сетевых сбоях.
   - Повторный запрос возвращает сохраненную задачу с флагом `is_duplicate: true`.

3. **Контроль актуальности кодов (TTL / `expires_at`)**:
   - Очередь не доставляет устаревшие SMS-коды. Если телефон долго был вне сети, просроченные задачи автоматически переводятся в статус `EXPIRED`.

4. **Асинхронные Webhooks (`webhook_url`)**:
   - Отправка статусов (`SENT`, `DELIVERED`, `FAILED`) во внешнюю систему.
   - До 3 повторных попыток с экспоненциальной задержкой.

5. **Защита от перегрузки (Rate Limiting)**:
   - Встроенный лимитер `SlowAPI` (120 запросов в минуту на эндпоинт).

6. **Мониторинг и метрики (Prometheus)**:
   - Эндпоинт `/metrics` отдает счетчики `sms_processed_total{status="..."}` и датчик `sms_active_devices`.

7. **Миграции базы данных (Alembic)**:
   - Автоматическое накатывание миграций: `alembic upgrade head`.
   - Полная совместимость с SQLite и PostgreSQL.

8. **SQLAdmin Панель управления**:
   - Управление API-ключами клиентов.
   - Управление шаблонами антифрода (`SMS Шаблоны`).
   - Мониторинг устройств: статус сети, заряд аккумулятора, индикатор зарядки, время последнего пинга.
   - Детальный журнал сообщений с фильтрацией по статусам и слотам SIM.

---

## 🚀 Быстрый запуск

### Вариант 1: Запуск в Docker (1 команда)

```bash
docker compose up -d --build
```

Сервер автоматически применит миграции Alembic, создаст таблицы и запустится на порту `8000`.

* **Панель управления**: [http://localhost:8000/admin](http://localhost:8000/admin) (логин: `admin`, пароль: `admin123`)
* **OpenAPI Swagger**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Метрики Prometheus**: [http://localhost:8000/metrics](http://localhost:8000/metrics)
* **Healthcheck**: [http://localhost:8000/health](http://localhost:8000/health)

### Вариант 2: Запуск через Python virtualenv

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Применение миграций
alembic upgrade head

# Запуск сервера
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Запуск тестов
python test_backend.py
```

---

## 📡 Примеры использования API

### 1. Отправка проверочного кода с антифродом (самый надежный способ)

```bash
curl -X POST "http://localhost:8000/api/v1/sms/send" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sms_ak_demo_master_token_12345" \
  -d '{
    "phone_number": "+79991234567",
    "code": "8412",
    "template_category": "auth",
    "idempotency_key": "auth_tx_998124_step1",
    "ttl_seconds": 300,
    "webhook_url": "https://myservice.com/api/webhooks/sms",
    "sim_slot": 0
  }'
```

**Ответ сервера:**
```json
{
  "task_id": "ecef80a9-be94-4bcf-b69f-83665700fd86",
  "phone_number": "+79991234567",
  "message": "Добро пожаловать! Подтверждение номера телефона: 8412. Безопасный код. / ff64",
  "status": "SENDING",
  "created_at": "2026-09-14T01:24:44.620000Z",
  "expires_at": "2026-09-14T01:29:44.620000Z",
  "is_duplicate": false
}
```

### 2. Проверка статуса доставки

```bash
curl -X GET "http://localhost:8000/api/v1/sms/ecef80a9-be94-4bcf-b69f-83665700fd86" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sms_ak_demo_master_token_12345"
```

**Ответ:**
```json
{
  "task_id": "ecef80a9-be94-4bcf-b69f-83665700fd86",
  "phone_number": "+79991234567",
  "message": "Добро пожаловать! Подтверждение номера телефона: 8412. Безопасный код. / ff64",
  "status": "DELIVERED",
  "error_message": null,
  "created_at": "2026-09-14T01:24:44.620000Z",
  "expires_at": "2026-09-14T01:29:44.620000Z",
  "sent_at": "2026-09-14T01:24:46.173000Z",
  "delivered_at": "2026-09-14T01:24:46.487000Z",
  "webhook_url": "https://myservice.com/api/webhooks/sms",
  "sim_slot": 1
}
```

### 3. Предварительный просмотр вариаций шаблона (Preview API)

```bash
curl -X GET "http://localhost:8000/api/v1/templates/preview?code=4400&count=3" \
  -H "X-API-Key: sms_ak_demo_master_token_12345"
```

---

## 🖼 Интерфейс Android GSM-шлюза

| Экран Material 3 | Ротация SIM и доставка |
|:---:|:---:|
| <img src="docs/screenshots/md3_active.png" width="300" /> | <img src="docs/screenshots/md3_rotated.png" width="300" /> |
