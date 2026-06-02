from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models import PaymentStatus


class MerchantCreate(BaseModel):
    name: str
    phone: str
    business_name: Optional[str] = None
    email: Optional[str] = None


class MerchantOut(BaseModel):
    id: str
    name: str
    phone: str
    business_name: Optional[str]
    email: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PaymentRequestCreate(BaseModel):
    merchant_id: str
    amount: float
    description: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None


class PaymentOut(BaseModel):
    id: str
    merchant_id: str
    amount: float
    currency: str
    description: Optional[str]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    kora_reference: Optional[str]
    payment_link: Optional[str]
    status: PaymentStatus
    paid_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class DailySummary(BaseModel):
    merchant_id: str
    date: str
    total_transactions: int
    completed_transactions: int
    total_revenue: float
    currency: str


class WebhookPayload(BaseModel):
    event: str
    data: dict
