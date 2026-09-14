from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class SmsSendRequest(BaseModel):
    phone_number: str = Field(..., description="Target phone number with country code, e.g. +79991234567")
    
    # Text or Template generation options
    message: Optional[str] = Field(
        None,
        max_length=1000,
        description="Direct message body or Spintax text, e.g. '{Ваш|Твой} код: 1234'. If omitted, 'code' must be provided."
    )
    code: Optional[str] = Field(
        None,
        max_length=32,
        description="Verification code (e.g. '8294'). If provided without 'message', backend automatically rotates anti-fraud templates."
    )
    template_category: Optional[str] = Field(
        "auth",
        description="Template category for auto-selection: 'auth', 'action', 'recovery'"
    )
    template_id: Optional[int] = Field(
        None,
        description="Optional specific template ID to use"
    )
    variables: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional template variables (e.g. {'service': 'MyBank'})"
    )
    anti_fraud_noise: bool = Field(
        False,
        description="Append subtle unique entropy/reference so carrier filters never see identical message hashes."
    )
    use_homoglyphs: bool = Field(
        True,
        description="Заменять кириллические буквы визуально идентичными английскими (B, a, o, p, c, e, y, x) для обхода DPI-фильтров оператора"
    )
    homoglyph_rate: float = Field(
        0.30,
        ge=0.0,
        le=1.0,
        description="Доля заменяемых букв (по умолчанию 30%)"
    )

    # Delivery & control options
    allow_queue: bool = Field(
        False,
        description="Поставить в очередь, если телефон не в сети. По умолчанию False — сразу возвращать ошибку 503."
    )
    idempotency_key: Optional[str] = Field(None, max_length=64, description="Unique client key to prevent duplicate SMS")
    ttl_seconds: Optional[int] = Field(300, ge=1, le=86400, description="Expiration time in seconds (default 300 = 5 min)")
    webhook_url: Optional[str] = Field(None, max_length=500, description="URL for status updates (SENT, DELIVERED, FAILED)")
    sim_slot: Optional[int] = Field(0, ge=0, le=2, description="SIM slot: 0=default, 1=SIM 1, 2=SIM 2")


class SmsSendResponse(BaseModel):
    task_id: str
    phone_number: str
    message: str
    status: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_duplicate: bool = False

    class Config:
        from_attributes = True


class SmsStatusResponse(BaseModel):
    task_id: str
    phone_number: str
    message: str
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    webhook_url: Optional[str] = None
    sim_slot: int = 0

    class Config:
        from_attributes = True


class SmsListResponse(BaseModel):
    total: int
    items: List[SmsStatusResponse]


class TemplateCreate(BaseModel):
    name: str = Field(..., max_length=100)
    category: str = Field("auth", max_length=50)
    template_text: str = Field(..., description="Template with {code} and Spintax {A|B}")
    is_active: bool = True


class TemplateOut(BaseModel):
    id: int
    name: str
    category: str
    template_text: str
    is_active: bool
    usage_count: int
    created_at: datetime

    class Config:
        from_attributes = True
