from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.device import Device, generate_device_token
from app.models.api_key import ApiKey
from app.schemas.device import DeviceOut
from app.auth.security import get_current_api_key

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get("", response_model=List[DeviceOut])
async def list_devices(
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Список подключенных устройств и их статус."""
    stmt = select(Device).order_by(Device.id.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def create_device(
    name: str = "Android Device",
    api_key: ApiKey = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Создать новое устройство и сгенерировать для него токен."""
    device = Device(
        name=name,
        token=generate_device_token(),
        is_active=True,
        is_online=False
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device
