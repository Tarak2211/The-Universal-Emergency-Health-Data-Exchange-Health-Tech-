from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.models import User, MedicalRecord, MedicalProfile
from app.auth import get_current_user, require_role
from app.config import settings
import httpx, json

router = APIRouter(prefix="/medical", tags=["Medical"])

def _get_fernet():
    if not settings.FERNET_KEY:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(settings.FERNET_KEY.encode())
    except Exception:
        return None

class PrescriptionRequest(BaseModel):
    patient_id: str
    content: dict

class MedicalProfileUpdate(BaseModel):
    blood_type: str | None = None
    allergies: list[str] | None = None
    conditions: list[str] | None = None
    medications: list[str] | None = None
    emergency_contacts: list[dict] | None = None

@router.put("/profile")
async def update_profile(
    data: MedicalProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(MedicalProfile).where(MedicalProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = MedicalProfile(user_id=current_user.id)
        db.add(profile)

    if data.blood_type is not None: profile.blood_type = data.blood_type
    if data.allergies is not None: profile.allergies = json.dumps(data.allergies)
    if data.conditions is not None: profile.conditions = json.dumps(data.conditions)
    if data.medications is not None: profile.medications = json.dumps(data.medications)
    if data.emergency_contacts is not None: profile.emergency_contacts = json.dumps(data.emergency_contacts)

    await db.commit()
    return {"message": "Profile updated"}

@router.post("/prescription")
async def issue_prescription(
    req: PrescriptionRequest,
    db: AsyncSession = Depends(get_db),
    doctor: User = Depends(require_role("doctor", "admin"))
):
    record = MedicalRecord(
        patient_id=req.patient_id,
        doctor_id=str(doctor.id),
        record_type="prescription",
        content=json.dumps(req.content)
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return {"record_id": record.id, "message": "Prescription issued"}

@router.get("/records/{patient_id}")
async def get_records(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role == "patient" and str(current_user.id) != patient_id:
        raise HTTPException(status_code=403, detail="Access denied")
    result = await db.execute(select(MedicalRecord).where(MedicalRecord.patient_id == patient_id))
    records = result.scalars().all()
    return [{"id": r.id, "type": r.record_type,
             "content": json.loads(r.content) if r.content else {},
             "issued_at": r.issued_at} for r in records]

@router.get("/patient-summary/{patient_id}")
async def get_patient_summary(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("doctor","admin"))
):
    """Feature 4: Full patient health summary for hospital on arrival."""
    # User info
    u_result = await db.execute(select(User).where(User.id==patient_id))
    user = u_result.scalar_one_or_none()
    if not user: raise HTTPException(404,"Patient not found")

    # Medical profile
    p_result = await db.execute(select(MedicalProfile).where(MedicalProfile.user_id==patient_id))
    profile = p_result.scalar_one_or_none()

    def parse(v):
        if not v: return []
        try: return json.loads(v)
        except: return []

    # All medical records
    r_result = await db.execute(
        select(MedicalRecord).where(MedicalRecord.patient_id==patient_id)
        .order_by(MedicalRecord.issued_at.desc())
    )
    records = r_result.scalars().all()

    return {
        "patient": {"id":user.id,"name":user.name,"phone":user.phone,"abha_id":user.abha_id},
        "medical_profile": {
            "blood_type": profile.blood_type if profile else None,
            "allergies":  parse(profile.allergies) if profile else [],
            "conditions": parse(profile.conditions) if profile else [],
            "medications":parse(profile.medications) if profile else [],
            "emergency_contacts": parse(profile.emergency_contacts) if profile else [],
        },
        "records": [
            {"id":r.id,"type":r.record_type,
             "content": json.loads(r.content) if r.content else {},
             "issued_at":r.issued_at.isoformat() if r.issued_at else None,
             "abha_synced":r.abha_synced}
            for r in records
        ],
        "record_count": len(records),
    }
async def fetch_abha_records(
    abha_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("doctor", "admin"))
):
    result = await db.execute(select(User).where(User.abha_id == abha_id))
    patient = result.scalar_one_or_none()
    if not patient or not patient.abha_token_enc:
        raise HTTPException(status_code=404, detail="ABHA record not found or not authorized")
    fernet = _get_fernet()
    if not fernet:
        raise HTTPException(status_code=500, detail="Encryption not configured")
    token = fernet.decrypt(patient.abha_token_enc.encode()).decode()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.ABHA_BASE_URL}/v0.5/health-information/fetch-records",
            headers={"Authorization": f"Bearer {token}", "X-CM-ID": abha_id}
        )
    return resp.json()
