from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class DeviceHeartbeat(BaseModel):
    battery_level: Optional[int] = Field(None, ge=0, le=100)
    is_charging: bool = False


class DeviceStatusUpdate(BaseModel):
    task_id: str
    status: str = Field(..., pattern="^(SENT|DELIVERED|FAILED)$")
    error: Optional[str] = None


class DeviceOut(BaseModel):
    id: int
    name: str
    token: str
    is_active: bool
    is_online: bool
    battery_level: Optional[int] = None
    is_charging: bool = False
    last_ping_at: Optional[datetime] = None

    class Config:
        from_attributes = True
