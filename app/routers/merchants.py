from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Merchant, Payment, PaymentStatus
from app.schemas import DailySummary, MerchantCreate, MerchantOut

router = APIRouter(prefix="/merchants", tags=["merchants"])


@router.post("/", response_model=MerchantOut, status_code=201)
def register_merchant(body: MerchantCreate, db: Session = Depends(get_db)):
    existing = db.query(Merchant).filter(Merchant.phone == body.phone).first()
    if existing:
        raise HTTPException(status_code=409, detail="Phone number already registered")
    merchant = Merchant(**body.model_dump())
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return merchant


@router.get("/{merchant_id}", response_model=MerchantOut)
def get_merchant(merchant_id: str, db: Session = Depends(get_db)):
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


@router.get("/by-phone/{phone}", response_model=MerchantOut)
def get_merchant_by_phone(phone: str, db: Session = Depends(get_db)):
    merchant = db.query(Merchant).filter(Merchant.phone == phone).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return merchant


@router.get("/{merchant_id}/summary", response_model=DailySummary)
def daily_summary(merchant_id: str, db: Session = Depends(get_db)):
    merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")

    today = date.today()
    day_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

    payments = (
        db.query(Payment)
        .filter(Payment.merchant_id == merchant_id, Payment.created_at >= day_start)
        .all()
    )

    completed = [p for p in payments if p.status == PaymentStatus.completed]
    total_revenue = sum(float(p.amount) for p in completed)

    return DailySummary(
        merchant_id=merchant_id,
        date=today.isoformat(),
        total_transactions=len(payments),
        completed_transactions=len(completed),
        total_revenue=total_revenue,
        currency="NGN",
    )
