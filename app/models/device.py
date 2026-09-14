import secrets
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base


def generate_device_token() -> str:
    return f"sms_dev_{secrets.token_hex(16)}"


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    token = Column(String(64), unique=True, index=True, nullable=False, default=generate_device_token)
    name = Column(String(100), nullable=False, default="Android Device")
    is_active = Column(Boolean, default=True, nullable=False)
    is_online = Column(Boolean, default=False, nullable=False)
    battery_level = Column(Integer, nullable=True)
    is_charging = Column(Boolean, default=False, nullable=False)
    last_ping_at = Column(DateTime(timezone=True), nullable=True)

    # Rotation & SIM metrics
    sim_count = Column(Integer, default=2, server_default="2", nullable=False)
    last_sim_slot = Column(Integer, default=1, server_default="1", nullable=False)
    total_sent_count = Column(Integer, default=0, server_default="0", nullable=False)
    hourly_sent_count = Column(Integer, default=0, server_default="0", nullable=False)
    max_hourly_per_sim = Column(Integer, default=30, server_default="30", nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    tasks = relationship("SmsTask", back_populates="device")

    def __repr__(self) -> str:
        return f"<Device {self.name} (online={self.is_online})>"

    def __str__(self) -> str:
        status = "🟢 Online" if self.is_online else "🔴 Offline"
        return f"{self.name} [{status}]"
