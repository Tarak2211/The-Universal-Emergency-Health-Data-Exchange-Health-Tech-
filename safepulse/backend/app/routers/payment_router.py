from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from app.database import get_db
from app.models import Payment, User
from app.auth import get_current_user
from app.config import settings
import razorpay, hmac, hashlib

router = APIRouter(prefix="/payments", tags=["Payments"])
rz_client = razorpay.Client(auth=(settings.RAZORPAY_KEY, settings.RAZORPAY_SECRET))

class OrderRequest(BaseModel):
    amount_paise: int   # ₹100 = 10000 paise
    description: str

class VerifyRequest(BaseModel):
    order_id: str
    payment_id: str
    signature: str

@router.post("/create-order")
async def create_order(
    req: OrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    order = rz_client.order.create({
        "amount": req.amount_paise,
        "currency": "INR",
        "payment_capture": 1,
        "notes": {"user_id": str(current_user.id), "description": req.description}
    })
    payment = Payment(user_id=current_user.id, amount=req.amount_paise / 100, razorpay_order_id=order["id"])
    db.add(payment)
    await db.commit()
    return {"order_id": order["id"], "amount": req.amount_paise, "currency": "INR"}

@router.post("/verify")
async def verify_payment(
    req: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    message = f"{req.order_id}|{req.payment_id}"
    expected = hmac.new(
        settings.RAZORPAY_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, req.signature):
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    await db.execute(
        update(Payment)
        .where(Payment.razorpay_order_id == req.order_id)
        .values(status="success", upi_ref=req.payment_id)
    )
    await db.commit()
    return {"message": "Payment verified successfully"}
