import re
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, field_validator
from app.database import get_db
from app.models import User
from app.auth import hash_password, verify_password, create_access_token
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

VALID_ROLES = {"patient", "doctor", "admin"}
PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")

class RegisterRequest(BaseModel):
    name: str
    phone: str
    password: str
    role: str = "patient"

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Name too long (max 100 characters)")
        return v

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v):
        v = v.strip()
        if not PHONE_RE.match(v):
            raise ValueError("Invalid phone number format")
        return v

    @field_validator("password")
    @classmethod
    def password_strong(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        if len(v) > 128:
            raise ValueError("Password too long")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v):
        if v not in VALID_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(VALID_ROLES)}")
        return v


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Check duplicate phone
    existing = await db.execute(select(User).where(User.phone == req.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Phone number already registered")

    user = User(
        name=req.name,
        phone=req.phone,
        hashed_password=hash_password(req.password),
        role=req.role,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        logger.error(f"Register DB error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")

    logger.info(f"New user registered: {user.phone} ({user.role})")
    return {"id": str(user.id), "message": "Registered successfully"}


@router.post("/login")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == form.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form.password, user.hashed_password):
        logger.warning(f"Failed login attempt for phone: {form.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": str(user.id), "role": user.role})
    logger.info(f"User logged in: {user.phone} ({user.role})")
    return {"access_token": token, "token_type": "bearer"}
