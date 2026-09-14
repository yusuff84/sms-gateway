import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class SmsStatus:
    QUEUED = "QUEUED"
    SENDING = "SENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class SmsTask(Base):
    __tablename__ = "sms_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key_id = Column(Integer, ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)

    phone_number = Column(String(32), nullable=False, index=True)
    message = Column(Text, nullable=False)
    status = Column(String(20), default=SmsStatus.QUEUED, nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    retries = Column(Integer, default=0, nullable=False)

    # Production fields: idempotency, TTL, webhooks, SIM routing
    idempotency_key = Column(String(64), index=True, nullable=True)
    expires_at = Column(DateTime(timezone=True), index=True, nullable=True)
    webhook_url = Column(String(500), nullable=True)
    sim_slot = Column(Integer, default=0, server_default="0", nullable=False)  # 0: Default SIM, 1: SIM1, 2: SIM2

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    api_key = relationship("ApiKey", back_populates="tasks")
    device = relationship("Device", back_populates="tasks")

    @property
    def is_expired(self) -> bool:
        if self.expires_at is not None:
            exp = self.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) > exp
        return False

    def __repr__(self) -> str:
        return f"<SmsTask {self.id} -> {self.phone_number} [{self.status}]>"
