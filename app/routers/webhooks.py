from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.kora import kora_client
from app.models import Payment, PaymentStatus

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/kora")
async def kora_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_kora_signature: str = Header(None, alias="x-kora-signature"),
):
    body = await request.body()

    if x_kora_signature and not kora_client.verify_webhook_signature(body, x_kora_signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")
    data = payload.get("data", {})

    if event == "charge.success":
        reference = data.get("reference") or data.get("transaction_reference")
        if reference:
            payment = db.query(Payment).filter(Payment.kora_reference == reference).first()
            if payment and payment.status == PaymentStatus.pending:
                payment.status = PaymentStatus.completed
                payment.paid_at = datetime.now(timezone.utc)
                db.commit()

    elif event in ("charge.failed", "charge.cancelled"):
        reference = data.get("reference") or data.get("transaction_reference")
        if reference:
            payment = db.query(Payment).filter(Payment.kora_reference == reference).first()
            if payment and payment.status == PaymentStatus.pending:
                payment.status = PaymentStatus.failed
                db.commit()

    return {"status": "ok"}
