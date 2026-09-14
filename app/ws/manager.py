import asyncio
import json
import logging
import random
import time
from typing import Dict, Optional, List
from fastapi import WebSocket
from datetime import datetime, timezone
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.device import Device
from app.models.sms_task import SmsTask, SmsStatus

logger = logging.getLogger("sms_gateway.ws")


class ConnectionManager:
    def __init__(self):
        # Map: device_id -> WebSocket
        self.active_connections: Dict[int, WebSocket] = {}
        # Map: device_id -> float timestamp of last dispatched SMS (for human pacing)
        self.last_dispatch_time: Dict[int, float] = {}

    async def connect(self, device_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[device_id] = websocket
        logger.info(f"Device ID {device_id} connected via WebSocket.")

        # Mark device as online in DB
        async with AsyncSessionLocal() as session:
            stmt = select(Device).where(Device.id == device_id)
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()
            if device:
                device.is_online = True
                device.last_ping_at = datetime.now(timezone.utc)
                await session.commit()

        # Dispatch any queued tasks
        asyncio.create_task(self.dispatch_queued_tasks(device_id))

    async def disconnect(self, device_id: int):
        if device_id in self.active_connections:
            try:
                del self.active_connections[device_id]
            except KeyError:
                pass
            logger.info(f"Device ID {device_id} disconnected.")

        # Mark device as offline in DB
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(Device).where(Device.id == device_id)
                result = await session.execute(stmt)
                device = result.scalar_one_or_none()
                if device:
                    device.is_online = False
                    await session.commit()
        except Exception as e:
            logger.debug(f"Could not update device {device_id} status on disconnect: {e}")

    def is_device_online(self, device_id: Optional[int] = None) -> bool:
        if device_id is not None:
            return device_id in self.active_connections
        return len(self.active_connections) > 0

    def get_first_online_device_id(self) -> Optional[int]:
        if self.active_connections:
            return next(iter(self.active_connections.keys()))
        return None

    async def send_task(self, device_id: int, task: SmsTask) -> bool:
        # Check if task is already expired
        if task.is_expired:
            logger.warning(f"Task {task.id} has expired (TTL exceeded). Marking EXPIRED.")
            async with AsyncSessionLocal() as session:
                stmt = select(SmsTask).where(SmsTask.id == task.id)
                res = await session.execute(stmt)
                db_task = res.scalar_one_or_none()
                if db_task:
                    db_task.status = SmsStatus.EXPIRED
                    db_task.error_message = "Task expired in queue before delivery"
                    await session.commit()
            return False

        websocket = self.active_connections.get(device_id)
        if not websocket:
            return False

        # Anti-fraud SIM rotation logic:
        # If task.sim_slot == 0 (Auto):
        # - If device has multiple SIMs (>1): alternate SIM 1 <-> SIM 2
        # - If device has single SIM (==1): strictly use SIM 1
        assigned_sim = task.sim_slot
        async with AsyncSessionLocal() as session:
            dev_stmt = select(Device).where(Device.id == device_id)
            dev_res = await session.execute(dev_stmt)
            dev = dev_res.scalar_one_or_none()
            if dev:
                if assigned_sim == 0:
                    if dev.sim_count > 1:
                        next_slot = 2 if dev.last_sim_slot == 1 else 1
                        assigned_sim = next_slot
                        dev.last_sim_slot = next_slot
                    else:
                        assigned_sim = 1
                        dev.last_sim_slot = 1

                dev.total_sent_count += 1
                dev.hourly_sent_count += 1

                # Update task's actual sim slot
                task_stmt = select(SmsTask).where(SmsTask.id == task.id)
                task_res = await session.execute(task_stmt)
                t = task_res.scalar_one_or_none()
                if t:
                    t.sim_slot = assigned_sim

                await session.commit()

        # Natural Human Pacing: ensure smooth dispatch interval (2.5 - 4.5s) to prevent carrier burst flags
        now = time.time()
        last_time = self.last_dispatch_time.get(device_id, 0)
        elapsed = now - last_time
        if elapsed < 2.5:
            await asyncio.sleep(random.uniform(2.5, 4.0) - elapsed)
        self.last_dispatch_time[device_id] = time.time()

        payload = {
            "type": "send_sms",
            "task_id": task.id,
            "phone_number": task.phone_number,
            "message": task.message,
            "sim_slot": assigned_sim
        }
        try:
            await websocket.send_text(json.dumps(payload))
            logger.info(f"Dispatched task {task.id} to device {device_id} (Rotated SIM slot {assigned_sim})")
            return True
        except Exception as e:
            logger.error(f"Failed to send task {task.id} to device {device_id}: {e}")
            await self.disconnect(device_id)
            return False

    async def dispatch_task_to_available_device(self, task: SmsTask) -> bool:
        device_id = self.get_first_online_device_id()
        if device_id is not None:
            sent = await self.send_task(device_id, task)
            if sent:
                async with AsyncSessionLocal() as session:
                    stmt = select(SmsTask).where(SmsTask.id == task.id)
                    res = await session.execute(stmt)
                    db_task = res.scalar_one_or_none()
                    if db_task:
                        db_task.device_id = device_id
                        db_task.status = SmsStatus.SENDING
                        await session.commit()
                return True
        return False

    async def dispatch_queued_tasks(self, device_id: int):
        """
        Send pending queued SMS tasks to the connected device with human-like pacing (anti-burst).
        """
        async with AsyncSessionLocal() as session:
            stmt = (
                select(SmsTask)
                .where(SmsTask.status == SmsStatus.QUEUED)
                .order_by(SmsTask.created_at.asc())
                .limit(50)
            )
            result = await session.execute(stmt)
            queued_tasks = result.scalars().all()

        for task in queued_tasks:
            if task.is_expired:
                async with AsyncSessionLocal() as s:
                    st = select(SmsTask).where(SmsTask.id == task.id)
                    r = await s.execute(st)
                    t = r.scalar_one_or_none()
                    if t:
                        t.status = SmsStatus.EXPIRED
                        t.error_message = "Task expired while queued"
                        await s.commit()
                continue

            success = await self.send_task(device_id, task)
            if success:
                async with AsyncSessionLocal() as s:
                    st = select(SmsTask).where(SmsTask.id == task.id)
                    r = await s.execute(st)
                    t = r.scalar_one_or_none()
                    if t:
                        t.device_id = device_id
                        t.status = SmsStatus.SENDING
                        await s.commit()
                # Anti-burst human-like delay (1.5 seconds between dispatch)
                await asyncio.sleep(1.5)
            else:
                break


manager = ConnectionManager()
