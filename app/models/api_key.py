import secrets
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


def generate_api_key() -> str:
    return f"sms_ak_{secrets.token_hex(16)}"


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(64), unique=True, index=True, nullable=False, default=generate_api_key)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    tasks = relationship("SmsTask", back_populates="api_key", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ApiKey {self.name} ({self.key[:10]}...)>"

    def __str__(self) -> str:
        return f"{self.name} ({self.key[:12]}...)"
