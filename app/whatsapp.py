import os
import httpx

PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
GRAPH_BASE = f"https://graph.facebook.com/v18.0"


async def send_message(to: str, text: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_BASE}/{PHONE_NUMBER_ID}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text},
            },
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
    if resp.status_code != 200:
        print(f"[wa] send_message failed to={to} status={resp.status_code}: {resp.text}")


async def send_document(to: str, pdf_bytes: bytes, filename: str) -> None:
    async with httpx.AsyncClient() as client:
        # Upload the file to get a media_id
        upload_resp = await client.post(
            f"{GRAPH_BASE}/{PHONE_NUMBER_ID}/media",
            headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
            files={"file": (filename, pdf_bytes, "application/pdf")},
            data={"messaging_product": "whatsapp", "type": "application/pdf"},
            timeout=30,
        )
        if upload_resp.status_code != 200:
            print(f"[wa] media upload failed: {upload_resp.text}")
            return
        media_id = upload_resp.json()["id"]

        # Send as document
        send_resp = await client.post(
            f"{GRAPH_BASE}/{PHONE_NUMBER_ID}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "document",
                "document": {"id": media_id, "filename": filename},
            },
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
    if send_resp.status_code != 200:
        print(f"[wa] send_document failed to={to} status={send_resp.status_code}: {send_resp.text}")
