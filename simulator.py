import asyncio
import json
import logging
import random
import sys
from datetime import datetime

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Android-Simulator] %(message)s"
)
logger = logging.getLogger("simulator")

SERVER_WS_URL = "ws://localhost:8088/ws/device?token=sms_dev_android_gateway_token_9999"


async def heartbeat_worker(ws):
    """Sends periodic battery and charging telemetry to backend."""
    try:
        while True:
            battery = random.randint(85, 95)
            payload = {
                "type": "heartbeat",
                "battery_level": battery,
                "is_charging": True
            }
            await ws.send(json.dumps(payload))
            logger.info(f"⚡ Heartbeat sent (Battery: {battery}%, Charging: ON)")
            await asyncio.sleep(20)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"Heartbeat loop interrupted: {e}")


async def handle_sms_task(ws, data):
    """Simulates GSM radio sending and carrier delivery."""
    task_id = data.get("task_id")
    phone = data.get("phone_number")
    message = data.get("message")
    sim_slot = data.get("sim_slot", 0)

    print("\n" + "=" * 60)
    print(f"📱 [INCOMING SMS TASK] {datetime.now().strftime('%H:%M:%S')}")
    print(f"   ID:       {task_id}")
    print(f"   To:       {phone}")
    print(f"   SIM Slot: {sim_slot} (Primary GSM)")
    print(f"   Message:  \033[92m{message}\033[0m")
    print("=" * 60)

    # 1. Simulate base station transmission delay
    await asyncio.sleep(0.6)
    sent_payload = {
        "type": "status",
        "task_id": task_id,
        "status": "SENT"
    }
    await ws.send(json.dumps(sent_payload))
    print(f"📡 [STATUS UPDATE] Task {task_id[:8]}... -> SENT to cellular network")

    # 2. Simulate carrier delivery to recipient's phone
    await asyncio.sleep(1.2)
    delivered_payload = {
        "type": "status",
        "task_id": task_id,
        "status": "DELIVERED"
    }
    await ws.send(json.dumps(delivered_payload))
    print(f"✅ [STATUS UPDATE] Task {task_id[:8]}... -> DELIVERED to recipient\n")


async def run_simulator():
    url = sys.argv[1] if len(sys.argv) > 1 else SERVER_WS_URL
    print(f"🚀 Starting Android GSM Gateway Simulator...")
    print(f"   Connecting to: {url}\n")

    while True:
        try:
            async with websockets.connect(url) as ws:
                print(f"🟢 Connected to SMS Gateway Backend via WebSocket!")
                heartbeat_task = asyncio.create_task(heartbeat_worker(ws))

                try:
                    async for message_text in ws:
                        try:
                            msg = json.loads(message_text)
                        except json.JSONDecodeError:
                            continue

                        msg_type = msg.get("type")
                        if msg_type == "send_sms":
                            asyncio.create_task(handle_sms_task(ws, msg))
                        elif msg_type == "heartbeat_ack":
                            pass
                        elif msg_type == "pong":
                            pass
                        else:
                            logger.info(f"Received message: {msg}")
                finally:
                    heartbeat_task.cancel()

        except (websockets.ConnectionClosed, ConnectionRefusedError) as e:
            print(f"🔴 Connection dropped ({e}). Reconnecting in 3 seconds...")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"⚠️ Simulator error: {e}. Reconnecting in 3 seconds...")
            await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(run_simulator())
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
