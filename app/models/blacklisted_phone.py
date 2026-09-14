from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base


class BlacklistedPhone(Base):
    __tablename__ = "blacklisted_phones"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    phone_number = Column(String(32), unique=True, index=True, nullable=False)
    reason = Column(String(255), default="Частые повторные запросы кодов за неделю", nullable=False)
    is_active = Column(Boolean, default=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<BlacklistedPhone {self.phone_number} (active={self.is_active})>"

    def __str__(self) -> str:
        status = "🚫 Заблокирован" if self.is_active else "⚪ Разблокирован"
        return f"{self.phone_number} [{status}]"
