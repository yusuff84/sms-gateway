import asyncio
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.device import Device
from app.models.sms_task import SmsTask, SmsStatus
from app.ws.manager import manager
from app.services.webhook import trigger_webhook_task

logger = logging.getLogger("sms_gateway.ws")
router = APIRouter()


@router.websocket("/ws/device")
async def device_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="Device authentication token")
):
    # 1. Authenticate device token
    async with AsyncSessionLocal() as session:
        stmt = select(Device).where(Device.token == token, Device.is_active == True)
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()

        if not device:
            logger.warning(f"Rejected WebSocket connection attempt with invalid token: {token[:8]}...")
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        device_id = device.id

    # 2. Accept and register connection
    await manager.connect(device_id, websocket)

    try:
        while True:
            data_text = await websocket.receive_text()
            try:
                data = json.loads(data_text)
            except json.JSONDecodeError:
                logger.warning(f"Received malformed JSON from device {device_id}: {data_text}")
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "heartbeat":
                battery = data.get("battery_level")
                charging = data.get("is_charging", False)
                async with AsyncSessionLocal() as session:
                    stmt = select(Device).where(Device.id == device_id)
                    res = await session.execute(stmt)
                    dev = res.scalar_one_or_none()
                    if dev:
                        if battery is not None:
                            dev.battery_level = int(battery)
                        dev.is_charging = bool(charging)
                        dev.last_ping_at = datetime.now(timezone.utc)
                        await session.commit()

                await websocket.send_text(json.dumps({"type": "heartbeat_ack"}))

            elif msg_type == "status":
                task_id = data.get("task_id")
                task_status = data.get("status")
                error = data.get("error")

                if task_id and task_status:
                    async with AsyncSessionLocal() as session:
                        stmt = select(SmsTask).where(SmsTask.id == task_id)
                        res = await session.execute(stmt)
                        task = res.scalar_one_or_none()
                        if task:
                            task.status = task_status
                            now = datetime.now(timezone.utc)
                            if task_status == SmsStatus.SENT:
                                task.sent_at = now
                            elif task_status == SmsStatus.DELIVERED:
                                task.delivered_at = now
                            elif task_status == SmsStatus.FAILED:
                                task.error_message = error

                            await session.commit()
                            logger.info(f"Task {task_id} updated to {task_status}")

                            # Dispatch webhook asynchronously if configured
                            if task.webhook_url:
                                webhook_payload = {
                                    "event": "sms_status_updated",
                                    "task_id": task.id,
                                    "phone_number": task.phone_number,
                                    "status": task.status,
                                    "error": task.error_message,
                                    "sent_at": task.sent_at.isoformat() if task.sent_at else None,
                                    "delivered_at": task.delivered_at.isoformat() if task.delivered_at else None
                                }
                                asyncio.create_task(
                                    trigger_webhook_task(task.webhook_url, webhook_payload)
                                )

            else:
                logger.debug(f"Unknown message type '{msg_type}' from device {device_id}")

    except WebSocketDisconnect:
        await manager.disconnect(device_id)
    except Exception as e:
        logger.error(f"WebSocket error for device {device_id}: {e}")
        await manager.disconnect(device_id)
