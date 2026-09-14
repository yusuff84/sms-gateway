import asyncio
import json
import time
import uuid
from fastapi.testclient import TestClient
from app.main import app
from app.seed import DEFAULT_API_KEY, DEFAULT_DEVICE_TOKEN
from app.models.sms_task import SmsStatus


def test_suite():
    print("=== Running Production SMS Gateway Backend Integration Tests ===")
    
    with TestClient(app) as client:
        # 1. Health check & Metrics
        res = client.get("/health")
        assert res.status_code == 200, f"Health check failed: {res.text}"
        data = res.json()
        print(f"✓ Health check: {data}")

        res = client.get("/metrics")
        assert res.status_code == 200
        assert "sms_processed_total" in res.text
        print("✓ Prometheus /metrics endpoint accessible")

        # 2. Unauthorized send attempt
        res = client.post("/api/v1/sms/send", json={"phone_number": "+79991112233", "message": "Test code 1234"})
        assert res.status_code == 401, f"Expected 401 Unauthorized, got: {res.status_code}"
        print("✓ Unauthorized request properly rejected (401)")

        headers = {"X-API-Key": DEFAULT_API_KEY}

        # 3. Offline Device Rejection Test (503 Service Unavailable)
        res_offline = client.post("/api/v1/sms/send", json={"phone_number": "+79991112233", "message": "Test code"}, headers=headers)
        assert res_offline.status_code == 503
        assert "SMS-шлюз сейчас недоступен" in res_offline.json()["detail"]
        print("✓ Offline phone check verified: returns 503 Service Unavailable when device is offline")

        # 4. Idempotency Key Test with allow_queue=True
        idemp_key = f"test_order_uniq_{uuid.uuid4().hex[:8]}"
        payload_1 = {
            "phone_number": "+7 999 111-22-33",
            "message": "Код для входа: 4421",
            "idempotency_key": idemp_key,
            "ttl_seconds": 300,
            "allow_queue": True
        }
        res_1 = client.post("/api/v1/sms/send", json=payload_1, headers=headers)
        assert res_1.status_code == 201
        data_1 = res_1.json()
        task_id_1 = data_1["task_id"]
        assert data_1["is_duplicate"] is False
        print(f"✓ Primary SMS created: Task ID = {task_id_1}")

        # Send second request with identical idempotency_key
        res_2 = client.post("/api/v1/sms/send", json=payload_1, headers=headers)
        assert res_2.status_code == 201
        data_2 = res_2.json()
        assert data_2["task_id"] == task_id_1
        assert data_2["is_duplicate"] is True
        print("✓ Idempotency verified: duplicate request returned existing task with is_duplicate=True")

        # 5. TTL / Expired Verification Code Test
        payload_expired = {
            "phone_number": "+7 999 888-77-66",
            "message": "Срочный код: 9999",
            "ttl_seconds": 1,  # Expires in 1 second!
            "allow_queue": True
        }
        res_exp = client.post("/api/v1/sms/send", json=payload_expired, headers=headers)
        assert res_exp.status_code == 201
        expired_task_id = res_exp.json()["task_id"]
        print(f"✓ Created short-TTL task: {expired_task_id}")

        print("  Waiting 1.5 seconds for TTL expiration...")
        time.sleep(1.5)

        # 5. WebSocket Device connection and processing
        print("✓ Testing WebSocket connection as Android Device...")
        with client.websocket_connect(f"/ws/device?token={DEFAULT_DEVICE_TOKEN}") as ws:
            # When connected, device receives pending task_1, but NOT expired_task!
            msg_raw = ws.receive_text()
            msg = json.loads(msg_raw)
            active_task_id = msg["task_id"]
            print(f"✓ Android received active task via WebSocket: {active_task_id}")
            assert msg["type"] == "send_sms"
            assert "sim_slot" in msg

            # Android sends heartbeat with battery status
            ws.send_text(json.dumps({"type": "heartbeat", "battery_level": 94, "is_charging": True}))
            while True:
                ack = json.loads(ws.receive_text())
                if ack.get("type") == "heartbeat_ack":
                    break
            print("✓ Heartbeat sent and acknowledged")

            # Android reports SMS as SENT
            ws.send_text(json.dumps({
                "type": "status",
                "task_id": active_task_id,
                "status": "SENT"
            }))
            time.sleep(0.3)

            # Android reports SMS as DELIVERED
            ws.send_text(json.dumps({
                "type": "status",
                "task_id": active_task_id,
                "status": "DELIVERED"
            }))
            time.sleep(0.3)

            # Test live code-only send while phone is online (should succeed with 201)
            res_auto = client.post(
                "/api/v1/sms/send",
                json={"phone_number": "+79993332211", "code": "6541", "idempotency_key": f"auto_{uuid.uuid4().hex[:6]}"},
                headers=headers
            )
            assert res_auto.status_code == 201
            auto_data = res_auto.json()
            assert "6541" in auto_data["message"]
            print(f"✓ Code-only auto-template generated while online: '{auto_data['message']}'")

        # 6. Verify active task is DELIVERED and expired task is EXPIRED
        res_check_1 = client.get(f"/api/v1/sms/{active_task_id}", headers=headers)
        assert res_check_1.status_code == 200
        assert res_check_1.json()["status"] == "DELIVERED"
        print(f"✓ Active task status in DB: {res_check_1.json()['status']}")

        res_check_exp = client.get(f"/api/v1/sms/{expired_task_id}", headers=headers)
        assert res_check_exp.status_code == 200
        assert res_check_exp.json()["status"] == "EXPIRED"
        print(f"✓ Expired task status in DB correctly marked: {res_check_exp.json()['status']}")

        # 7. Test Anti-Fraud Spintax & Template Rotation Preview
        print("✓ Testing Anti-Fraud Template Generation & Rotation...")
        res_prev = client.get("/api/v1/templates/preview?code=9911&count=5", headers=headers)
        assert res_prev.status_code == 200
        variations = res_prev.json()["variations"]
        assert len(variations) == 5
        print(f"  Generated {len(variations)} sample variations:")
        for v in variations[:3]:
            print(f"    -> {v}")

        # 8. Check Admin panel
        res = client.get("/admin/login")
        assert res.status_code == 200
        print("✓ SQLAdmin login interface accessible (200 OK)")

    print("\n🎉 ALL PRODUCTION BACKEND TESTS PASSED SUCCESSFULLY! 🎉\n")


if __name__ == "__main__":
    test_suite()
