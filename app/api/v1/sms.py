import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.sms_task import SmsTask, SmsStatus
from app.models.sms_template import SmsTemplate
from app.schemas.sms import (
    SmsSendRequest,
    SmsSendResponse,
    SmsStatusResponse,
    SmsListResponse,
    TemplateCreate,
    TemplateOut
)
from app.auth.security import get_current_api_key
from app.config import settings
from app.ws.manager import manager
from app.core.limiter import limiter
from app.services.anti_fraud import (
    render_template_string,
    get_random_template_for_category,
    parse_spintax
)

router = APIRouter(tags=["SMS"])


def clean_phone_number(raw_phone: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", raw_phone)
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Phone number cannot be empty."
        )
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


@router.post("/sms/send", response_model=SmsSendResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("120/minute")
async def send_sms(
    request: Request,
    payload: SmsSendRequest,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Отправить SMS на указанный номер телефона с продвинутой защитой от антифрод-систем сотовых операторов.
    
    Поддерживает:
    - **Антифрод-рандомизация**: передайте только `code: "1234"` — бэкенд автоматически выберет шаблон и создаст уникальный текст через Spintax.
    - **Прямой Spintax**: передайте `message: "{Ваш|Твой} код: 1234"` — сервер развернет случайную вариацию.
    - **Идемпотентность (`idempotency_key`)**: предотвращение дублирования SMS.
    - **TTL (`ttl_seconds`)**: исключение отправки устаревших кодов.
    - **Webhooks (`webhook_url`)**: асинхронные уведомления о доставке.
    - **SIM слот (`sim_slot`)**: выбор физической SIM-карты.
    """
    cleaned_phone = clean_phone_number(payload.phone_number)

    # 1. Validate payload has either message or code
    if not payload.message and not payload.code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either 'message' or 'code' must be provided."
        )

    # 2. Idempotency check: prevent duplicate SMS delivery
    if payload.idempotency_key:
        stmt = select(SmsTask).where(
            SmsTask.idempotency_key == payload.idempotency_key,
            SmsTask.api_key_id == api_key.id
        )
        res = await db.execute(stmt)
        existing_task = res.scalar_one_or_none()
        if existing_task:
            return SmsSendResponse(
                task_id=existing_task.id,
                phone_number=existing_task.phone_number,
                message=existing_task.message,
                status=existing_task.status,
                created_at=existing_task.created_at,
                expires_at=existing_task.expires_at,
                is_duplicate=True
            )

    # 3. Gateway availability check: immediately return 503 if phone is offline (unless allow_queue is True)
    if not payload.allow_queue and not manager.is_device_online():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMS-шлюз сейчас недоступен: телефон для отправки SMS не в сети. Попробуйте позже или используйте альтернативный способ."
        )

    # 4. Recipient Anti-Flood Cooldown (protect single SIM from burning quota on the same number)
    if settings.PHONE_NUMBER_COOLDOWN_SECONDS > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.PHONE_NUMBER_COOLDOWN_SECONDS)
        flood_stmt = select(SmsTask).where(
            SmsTask.phone_number == cleaned_phone,
            SmsTask.created_at >= cutoff
        ).order_by(SmsTask.created_at.desc()).limit(1)
        flood_res = await db.execute(flood_stmt)
        recent = flood_res.scalar_one_or_none()
        if recent:
            recent_time = recent.created_at
            if recent_time.tzinfo is None:
                recent_time = recent_time.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - recent_time).total_seconds()
            remaining = max(1, int(settings.PHONE_NUMBER_COOLDOWN_SECONDS - elapsed))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Повторная отправка на номер {cleaned_phone} возможна через {remaining} сек."
            )

    # 4. Resolve final SMS message with anti-fraud Spintax
    variables = dict(payload.variables or {})
    if payload.code:
        variables["code"] = payload.code

    final_message: str
    if payload.message:
        # User provided custom text (possibly with Spintax like "{Код|Пароль}: 1234")
        final_message = render_template_string(
            payload.message,
            variables,
            add_noise=payload.anti_fraud_noise
        )
    else:
        # Automatically select an anti-fraud template from the database
        template: Optional[SmsTemplate] = None
        if payload.template_id:
            stmt = select(SmsTemplate).where(
                SmsTemplate.id == payload.template_id,
                SmsTemplate.is_active == True
            )
            res = await db.execute(stmt)
            template = res.scalar_one_or_none()

        if not template:
            category = payload.template_category or "auth"
            template = await get_random_template_for_category(db, category)

        if template:
            final_message = render_template_string(
                template.template_text,
                variables,
                add_noise=payload.anti_fraud_noise
            )
        else:
            # Fallback default spintax if no templates seeded
            fallback = "{Ваш|Твой|Одноразовый} {код подтверждения|пароль для входа}: {code}. {Никому не сообщайте|Действует 5 мин}."
            final_message = render_template_string(
                fallback,
                variables,
                add_noise=payload.anti_fraud_noise
            )

    # 4. Calculate expiration time (TTL)
    ttl = payload.ttl_seconds if payload.ttl_seconds is not None else 300
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

    task = SmsTask(
        api_key_id=api_key.id,
        phone_number=cleaned_phone,
        message=final_message,
        status=SmsStatus.QUEUED,
        idempotency_key=payload.idempotency_key,
        expires_at=expires_at,
        webhook_url=payload.webhook_url,
        sim_slot=payload.sim_slot or 0
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 5. Attempt immediate dispatch to active connected Android device
    await manager.dispatch_task_to_available_device(task)
    await db.refresh(task)

    return SmsSendResponse(
        task_id=task.id,
        phone_number=task.phone_number,
        message=task.message,
        status=task.status,
        created_at=task.created_at,
        expires_at=task.expires_at,
        is_duplicate=False
    )


@router.get("/sms/{task_id}", response_model=SmsStatusResponse)
async def get_sms_status(
    task_id: str,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить актуальный статус отправки конкретного SMS по его task_id.
    """
    stmt = select(SmsTask).where(SmsTask.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SMS task with id '{task_id}' not found."
        )

    if task.status == SmsStatus.QUEUED and task.is_expired:
        task.status = SmsStatus.EXPIRED
        task.error_message = "Task expired while queued"
        await db.commit()
        await db.refresh(task)

    return SmsStatusResponse(
        task_id=task.id,
        phone_number=task.phone_number,
        message=task.message,
        status=task.status,
        error_message=task.error_message,
        created_at=task.created_at,
        expires_at=task.expires_at,
        sent_at=task.sent_at,
        delivered_at=task.delivered_at,
        webhook_url=task.webhook_url,
        sim_slot=task.sim_slot
    )


@router.get("/sms", response_model=SmsListResponse)
async def list_sms_tasks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, alias="status"),
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Список отправленных SMS с пагинацией и фильтрацией по статусу.
    """
    base_query = select(SmsTask)
    count_query = select(func.count(SmsTask.id))

    if status_filter:
        base_query = base_query.where(SmsTask.status == status_filter.upper())
        count_query = count_query.where(SmsTask.status == status_filter.upper())

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    stmt = base_query.order_by(SmsTask.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    items = [
        SmsStatusResponse(
            task_id=t.id,
            phone_number=t.phone_number,
            message=t.message,
            status=t.status,
            error_message=t.error_message,
            created_at=t.created_at,
            expires_at=t.expires_at,
            sent_at=t.sent_at,
            delivered_at=t.delivered_at,
            webhook_url=t.webhook_url,
            sim_slot=t.sim_slot
        )
        for t in tasks
    ]

    return SmsListResponse(total=total, items=items)


# === Anti-fraud Templates API ===

@router.get("/templates", response_model=List[TemplateOut], tags=["Anti-Fraud Templates"])
async def list_templates(
    category: Optional[str] = None,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Список всех доступных антифрод-шаблонов."""
    query = select(SmsTemplate).order_by(SmsTemplate.id.asc())
    if category:
        query = query.where(SmsTemplate.category == category)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED, tags=["Anti-Fraud Templates"])
async def create_template(
    payload: TemplateCreate,
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Создать новый антифрод-шаблон со Spintax синтаксисом {A|B|C}."""
    template = SmsTemplate(
        name=payload.name,
        category=payload.category,
        template_text=payload.template_text,
        is_active=payload.is_active
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("/templates/preview", tags=["Anti-Fraud Templates"])
async def preview_template_variations(
    template_id: Optional[int] = None,
    spintax: Optional[str] = None,
    code: str = "4921",
    count: int = Query(5, ge=1, le=20),
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Генерирует N случайных вариаций текста для проверки работы Spintax и антифрода.
    """
    raw_text = spintax
    if not raw_text and template_id:
        stmt = select(SmsTemplate).where(SmsTemplate.id == template_id)
        res = await db.execute(stmt)
        tmpl = res.scalar_one_or_none()
        if tmpl:
            raw_text = tmpl.template_text

    if not raw_text:
        raw_text = "{Ваш|Твой|Одноразовый} {код подтверждения|пароль для входа|проверочный код}: {code}. {Никому не сообщайте|Действителен 5 минут|Не передавайте третьим лицам}."

    samples = [
        render_template_string(raw_text, {"code": code}, add_noise=True)
        for _ in range(count)
    ]
    return {
        "original_template": raw_text,
        "sample_count": count,
        "variations": samples
    }
