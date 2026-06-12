import hashlib
import hmac
import json
import os
import httpx

KORA_BASE_URL = os.getenv("KORA_BASE_URL", "https://api.korapay.com/merchant/api/v1")
KORA_SECRET_KEY = os.getenv("KORA_SECRET_KEY", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {KORA_SECRET_KEY}",
        "Content-Type": "application/json",
    }


async def create_payment_link(
    reference: str,
    amount: float,
    description: str,
    customer_name: str = None,
) -> str:
    payload = {
        "amount": amount,
        "currency": "NGN",
        "reference": reference,
        "narration": description or "Payment request",
        "customer": {
            "name": customer_name or "Customer",
            "email": "customer@paypaddi.com",
        },
    }
    if APP_BASE_URL:
        payload["notification_url"] = f"{APP_BASE_URL}/webhooks/kora"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{KORA_BASE_URL}/charges/initialize",
            json=payload,
            headers=_headers(),
            timeout=30,
        )
        if not resp.is_success:
            print(f"[kora] {resp.status_code} error body: {resp.text}")
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return data.get("checkout_url") or data.get("link") or ""


def verify_webhook(payload: dict, signature: str) -> bool:
    data_str = json.dumps(payload, separators=(",", ":"))
    expected = hmac.new(
        KORA_SECRET_KEY.encode(),
        data_str.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
