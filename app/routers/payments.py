import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.kora import kora_client
from app.models import Merchant, Payment
from app.schemas import PaymentOut, PaymentRequestCreate

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/request", response_model=PaymentOut, status_code=201)
async def create_payment_request(body: PaymentRequestCreate, db: Session = Depends(get_db)):
    merchant = db.query(Merchant).filter(Merchant.id == body.merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    reference = str(uuid.uuid4())

    payment = Payment(
        id=reference,
        merchant_id=body.merchant_id,
        amount=body.amount,
        description=body.description,
        customer_name=body.customer_name,
        customer_phone=body.customer_phone,
        kora_reference=reference,
    )
    db.add(payment)
    db.commit()

    try:
        kora_response = await kora_client.create_payment_link(
            amount=body.amount,
            currency="NGN",
            reference=reference,
            description=body.description or "Payment request",
            merchant_name=merchant.business_name or merchant.name,
            customer_name=body.customer_name,
            customer_phone=body.customer_phone,
        )
        payment_link = kora_response.get("data", {}).get("checkout_url") or kora_response.get("data", {}).get("link")
        payment.payment_link = payment_link
        db.commit()
    except Exception as e:
        # Store what we have; webhook will update status when paid
        db.commit()
        raise HTTPException(status_code=502, detail=f"Kora API error: {str(e)}")

    db.refresh(payment)
    return payment


@router.get("/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: str, db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.get("/merchant/{merchant_id}", response_model=list[PaymentOut])
def list_merchant_payments(merchant_id: str, limit: int = 20, db: Session = Depends(get_db)):
    payments = (
        db.query(Payment)
        .filter(Payment.merchant_id == merchant_id)
        .order_by(Payment.created_at.desc())
        .limit(limit)
        .all()
    )
    return payments
