import hashlib
import hmac
import httpx
from app.config import settings


class KoraClient:
    def __init__(self):
        self.base_url = settings.KORA_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {settings.KORA_SECRET_KEY}",
            "Content-Type": "application/json",
        }

    async def create_payment_link(
        self,
        amount: float,
        currency: str,
        reference: str,
        description: str,
        merchant_name: str,
        customer_name: str | None = None,
        customer_phone: str | None = None,
    ) -> dict:
        payload = {
            "amount": amount,
            "currency": currency,
            "reference": reference,
            "narration": description or "Payment request",
            "merchant_name": merchant_name,
            "notification_url": f"{settings.APP_BASE_URL}/webhooks/kora",
        }
        if customer_name:
            payload["customer"] = {"name": customer_name}
        if customer_phone:
            payload.setdefault("customer", {})["phone"] = customer_phone

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/transactions/initialize",
                json=payload,
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_transaction(self, reference: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/transactions/{reference}",
                headers=self.headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    def verify_webhook_signature(self, payload_bytes: bytes, signature: str) -> bool:
        expected = hmac.new(
            settings.KORA_WEBHOOK_SECRET.encode(),
            payload_bytes,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


kora_client = KoraClient()
