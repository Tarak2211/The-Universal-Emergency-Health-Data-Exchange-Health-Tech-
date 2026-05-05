import json
import logging
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel, field_validator
from app.database import get_db
from app.models import EmergencyLog, User, MedicalProfile
from app.auth import get_current_user
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sos", tags=["SOS"])

# ── Auto severity from G-force ────────────────────────────
def auto_severity(g: float) -> str:
    if g >= 7.0:   return "severe"
    if g >= 3.5:   return "moderate"
    return "low"

def is_critical(g: float) -> bool:
    return g >= 7.0

# ── Family alert (background task) ───────────────────────
def send_family_alerts(user_id: str, sos_id: str, lat: float, lon: float, severity: str):
    if not settings.TWILIO_SID:
        return
    try:
        import sqlite3
        from twilio.rest import Client
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").lstrip("./")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT emergency_contacts FROM medical_profiles WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if not row or not row[0]:
            return
        contacts = json.loads(row[0])
        if not contacts:
            return
        client = Client(settings.TWILIO_SID, settings.TWILIO_TOKEN)
        tracking_url = f"{settings.APP_BASE_URL}/dispatch/track/{sos_id}"
        maps_url = f"https://maps.google.com/?q={lat},{lon}"
        sev_label = "🔴 CRITICAL" if severity == "severe" else "🟠 MODERATE"
        msg = (
            f"🚨 SafePulse EMERGENCY\n"
            f"Severity: {sev_label}\n"
            f"📍 Location: {maps_url}\n"
            f"🚑 Live Tracking: {tracking_url}"
        )
        for contact in contacts:
            phone = contact.get("phone", "")
            if not phone:
                continue
            try:
                client.messages.create(
                    body=msg,
                    from_=settings.TWILIO_WHATSAPP_FROM,
                    to=f"whatsapp:{phone}"
                )
            except Exception as e:
                logger.warning(f"WhatsApp failed for {phone}: {e}")
                try:
                    client.messages.create(body=msg, from_=settings.TWILIO_PHONE, to=phone)
                except Exception as e2:
                    logger.error(f"SMS also failed for {phone}: {e2}")
    except Exception as e:
        logger.error(f"Family alert error: {e}")


class SOSPayload(BaseModel):
    latitude: float
    longitude: float
    g_force_peak: float
    severity: str | None = None

    @field_validator("latitude")
    @classmethod
    def lat_range(cls, v):
        if not (-90 <= v <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        return round(v, 8)

    @field_validator("longitude")
    @classmethod
    def lon_range(cls, v):
        if not (-180 <= v <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        return round(v, 8)

    @field_validator("g_force_peak")
    @classmethod
    def g_positive(cls, v):
        if v < 0:
            raise ValueError("G-force cannot be negative")
        if v > 100:
            raise ValueError("G-force value unrealistically high")
        return round(v, 2)


@router.post("/trigger")
async def trigger_sos(
    payload: SOSPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    severity = payload.severity or auto_severity(payload.g_force_peak)
    critical = is_critical(payload.g_force_peak)

    log = EmergencyLog(
        user_id=current_user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        g_force_peak=payload.g_force_peak,
        severity=severity,
        status="triggered",
    )
    db.add(log)
    try:
        await db.commit()
        await db.refresh(log)
    except Exception as e:
        await db.rollback()
        logger.error(f"SOS DB error: {e}")
        raise HTTPException(status_code=500, detail="Failed to record SOS. Please try again.")

    logger.info(f"SOS triggered: {log.id} | user={current_user.id} | severity={severity} | G={payload.g_force_peak}")

    if settings.TWILIO_SID:
        background_tasks.add_task(
            send_family_alerts,
            str(current_user.id), str(log.id),
            payload.latitude, payload.longitude, severity,
        )

    return {
        "sos_id": log.id,
        "countdown_seconds": 15,
        "severity": severity,
        "critical_alert": critical,
        "message": "🚨 CRITICAL — High-priority alert sent!" if critical else "SOS initiated. Cancel within 15 seconds.",
        "tracking_url": f"{settings.APP_BASE_URL}/dispatch/track/{log.id}",
    }


@router.post("/{sos_id}/cancel")
async def cancel_sos(
    sos_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EmergencyLog).where(
            EmergencyLog.id == sos_id,
            EmergencyLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="SOS event not found")
    if log.status == "cancelled":
        return {"message": "Already cancelled"}

    await db.execute(
        update(EmergencyLog)
        .where(EmergencyLog.id == sos_id, EmergencyLog.user_id == current_user.id)
        .values(status="cancelled")
    )
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"SOS cancel DB error: {e}")
        raise HTTPException(status_code=500, detail="Cancel failed. Please try again.")

    logger.info(f"SOS cancelled: {sos_id} by user={current_user.id}")
    return {"message": "SOS cancelled"}


@router.get("/medical-id")
async def get_medical_id(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MedicalProfile).where(MedicalProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        return {"name": current_user.name, "message": "No medical profile found. Please update your profile."}

    def safe_parse(val):
        if not val:
            return []
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "name": current_user.name,
        "blood_type": profile.blood_type or "Unknown",
        "allergies":  safe_parse(profile.allergies),
        "conditions": safe_parse(profile.conditions),
        "medications":safe_parse(profile.medications),
        "emergency_contacts": safe_parse(profile.emergency_contacts),
    }


@router.get("/logs")
async def get_sos_logs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Admins and doctors see all logs; patients see their own
    if current_user.role in ("admin", "doctor"):
        result = await db.execute(
            select(EmergencyLog, User.name)
            .join(User, EmergencyLog.user_id == User.id)
            .order_by(EmergencyLog.triggered_at.desc())
            .limit(100)
        )
        rows = result.all()
        return [
            {
                "id": l.id, "status": l.status, "severity": l.severity,
                "g_force": l.g_force_peak, "triggered_at": l.triggered_at,
                "lat": l.latitude, "lon": l.longitude,
                "patient_name": name,
            }
            for l, name in rows
        ]
    else:
        result = await db.execute(
            select(EmergencyLog)
            .where(EmergencyLog.user_id == current_user.id)
            .order_by(EmergencyLog.triggered_at.desc())
            .limit(50)
        )
        logs = result.scalars().all()
        return [
            {
                "id": l.id, "status": l.status, "severity": l.severity,
                "g_force": l.g_force_peak, "triggered_at": l.triggered_at,
                "lat": l.latitude, "lon": l.longitude,
            }
            for l in logs
        ]
