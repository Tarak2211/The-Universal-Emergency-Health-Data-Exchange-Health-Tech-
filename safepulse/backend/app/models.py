import uuid
from datetime import datetime
from sqlalchemy import String, Float, Boolean, ForeignKey, Interval, Enum, TIMESTAMP, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import json

# UUID that works with both SQLite and PostgreSQL
class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is None: return value
        return str(value)
    def process_result_value(self, value, dialect):
        if value is None: return value
        return str(value)

# JSON column that works with SQLite
class JSONType(TypeDecorator):
    impl = Text
    cache_ok = True
    def process_bind_param(self, value, dialect):
        if value is None: return None
        return json.dumps(value)
    def process_result_value(self, value, dialect):
        if value is None: return None
        if isinstance(value, (dict, list)): return value
        return json.loads(value)

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="patient")
    abha_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    abha_token_enc: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)

    medical_profile: Mapped["MedicalProfile"] = relationship(back_populates="user", uselist=False)
    emergency_logs: Mapped[list["EmergencyLog"]] = relationship(back_populates="user", foreign_keys="EmergencyLog.user_id")

class MedicalProfile(Base):
    __tablename__ = "medical_profiles"
    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    blood_type: Mapped[str | None] = mapped_column(String(5))
    allergies: Mapped[str | None] = mapped_column(Text)       # stored as JSON string
    conditions: Mapped[str | None] = mapped_column(Text)
    medications: Mapped[str | None] = mapped_column(Text)
    emergency_contacts: Mapped[str | None] = mapped_column(Text)  # JSON

    user: Mapped["User"] = relationship(back_populates="medical_profile")

class EmergencyLog(Base):
    __tablename__ = "emergency_logs"
    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    triggered_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    g_force_peak: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[str] = mapped_column(String(20), default="moderate")
    status: Mapped[str] = mapped_column(String(20), default="triggered")
    responder_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    response_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped["User"] = relationship(back_populates="emergency_logs", foreign_keys=[user_id])

class MedicalRecord(Base):
    __tablename__ = "medical_records"
    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    patient_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    doctor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    record_type: Mapped[str] = mapped_column(String(30))
    content: Mapped[str | None] = mapped_column(Text)   # JSON
    issued_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
    abha_synced: Mapped[bool] = mapped_column(Boolean, default=False)

class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    upi_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)
