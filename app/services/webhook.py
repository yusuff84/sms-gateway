import asyncio
import logging
from typing import Dict, Any
import httpx

logger = logging.getLogger("sms_gateway.webhook")


async def trigger_webhook_task(webhook_url: str, payload: Dict[str, Any]):
    """
    Asynchronously fires an HTTP POST notification to the client's webhook_url.
    Retries up to 3 times on network failure with backoff.
    """
    if not webhook_url:
        return

    max_retries = 3
    retry_delay = 2.0  # seconds

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers={"User-Agent": "SMSGateway-Webhook/1.0", "Content-Type": "application/json"}
                )
                if response.status_code < 400:
                    logger.info(f"Webhook delivered successfully to {webhook_url} (HTTP {response.status_code})")
                    return
                else:
                    logger.warning(
                        f"Webhook {webhook_url} returned HTTP {response.status_code} on attempt {attempt}/{max_retries}"
                    )
        except Exception as e:
            logger.warning(f"Failed to deliver webhook to {webhook_url} on attempt {attempt}/{max_retries}: {e}")

        if attempt < max_retries:
            await asyncio.sleep(retry_delay * attempt)

    logger.error(f"Webhook delivery permanently failed for {webhook_url} after {max_retries} attempts.")
