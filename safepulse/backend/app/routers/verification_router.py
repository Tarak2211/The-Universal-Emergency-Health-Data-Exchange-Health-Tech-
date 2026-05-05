"""
Anti-False Alarm Verification System
=====================================
5-layer verification before dispatching ambulance:

Layer 1 — G-Force threshold filter (backend, instant)
Layer 2 — "I'm OK" countdown (15s human check)
Layer 3 — Silence/no-response logic (auto-escalate)
Layer 4 — Audio analysis result (from mobile mic)
Layer 5 — AI voice bot call via Twilio (automated phone call)

State machine per SOS:
  pending_human_check → cancelled | escalated_to_dispatch
"""
import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database import get_db
from app.models import EmergencyLog, User
from app.auth import get_current_user
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/verify", tags=["Anti-False Alarm"])

# In-memory verification state per SOS
# { sos_id: { state, created_at, audio_result, voice_confirmed, countdown_seconds } }
_verifications: dict[str, dict] = {}

STATES = {
    "pending":    "Waiting for human response",
    "ok_by_user": "User confirmed safe — cancelled",
    "ok_by_voice":"Voice bot confirmed safe — cancelled",
    "escalated":  "No response — escalated to dispatch",
    "audio_critical": "Audio analysis flagged critical",
}

# ── Layer 1: G-Force thresholds ───────────────────────────
GFORCE_IGNORE    = 2.0   # below this → ignore completely (scratch, pothole)
GFORCE_WARN      = 3.5   # moderate — trigger verification
GFORCE_CRITICAL  = 7.0   # severe — shorter countdown, immediate voice call

def classify_impact(g: float) -> str:
    if g < GFORCE_IGNORE:   return "ignore"
    if g < GFORCE_WARN:     return "minor"
    if g < GFORCE_CRITICAL: return "moderate"
    return "critical"


class AudioAnalysisPayload(BaseModel):
    sos_id: str
    # Mobile sends these flags after 10s mic analysis
    detected_metal_crush: bool = False
    detected_glass_break: bool = False
    detected_silence: bool = False
    detected_normal_speech: bool = False
    detected_argument: bool = False
    ambient_db_level: float = 0.0   # decibel level

class VoiceConfirmPayload(BaseModel):
    sos_id: str
    confirmed_safe: bool   # True = user said "I'm fine" / gave passcode


# ── Layer 4: Audio analysis ───────────────────────────────
def analyze_audio(payload: AudioAnalysisPayload) -> dict:
    """
    Rule-based audio classifier.
    Returns: { is_critical, reason, confidence }
    """
    critical_signals = []
    safe_signals = []

    if payload.detected_metal_crush:
        critical_signals.append("metal crushing sound detected")
    if payload.detected_glass_break:
        critical_signals.append("glass breaking detected")
    if payload.detected_silence and payload.ambient_db_level < 30:
        critical_signals.append("post-impact silence (possible unconsciousness)")

    if payload.detected_normal_speech:
        safe_signals.append("normal speech detected (user likely conscious)")
    if payload.detected_argument:
        safe_signals.append("argument/shouting detected (typical Ahmedabad fender-bender!)")

    # Decision logic
    if safe_signals and not critical_signals:
        return {"is_critical": False, "reason": safe_signals[0], "confidence": "high"}
    if critical_signals and not safe_signals:
        return {"is_critical": True, "reason": critical_signals[0], "confidence": "high"}
    if critical_signals and safe_signals:
        # Mixed signals — err on side of caution
        return {"is_critical": True, "reason": f"Mixed: {critical_signals[0]} but {safe_signals[0]}", "confidence": "medium"}

    # No clear signal — rely on other layers
    return {"is_critical": None, "reason": "No clear audio signal", "confidence": "low"}


# ── Layer 5: Twilio AI voice call ─────────────────────────
def make_verification_call(phone: str, sos_id: str, user_name: str):
    """
    Calls the user. If they answer and press 1 or say 'safe', cancel the SOS.
    Uses Twilio TwiML with <Gather> for keypress response.
    """
    if not settings.TWILIO_SID:
        logger.info("Twilio not configured — skipping voice verification call")
        return
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_SID, settings.TWILIO_TOKEN)
        callback_url = f"{settings.APP_BASE_URL}/verify/voice-response/{sos_id}"
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="alice" language="en-IN">
    Hello {user_name}. This is SafePulse. We detected a possible accident on your phone.
    If you are safe and do not need an ambulance, press 1 now.
    If you need emergency help, stay on the line or press 2.
  </Say>
  <Gather numDigits="1" action="{callback_url}" method="POST" timeout="8">
    <Say voice="alice">Press 1 if you are safe. Press 2 for emergency help.</Say>
  </Gather>
  <Say voice="alice">No response received. Dispatching emergency services now. Stay safe.</Say>
</Response>"""
        client.calls.create(
            twiml=twiml,
            to=phone,
            from_=settings.TWILIO_PHONE,
        )
        logger.info(f"Verification call placed to {phone} for SOS {sos_id}")
    except Exception as e:
        logger.error(f"Voice call failed: {e}")


# ── Routes ────────────────────────────────────────────────

@router.post("/start")
async def start_verification(
    sos_id: str,
    g_force: float,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Called immediately after SOS trigger.
    Starts the verification countdown and optionally places a voice call.
    """
    impact = classify_impact(g_force)
    if impact == "ignore":
        return {"action": "ignored", "reason": f"G-force {g_force}g below threshold {GFORCE_IGNORE}g"}

    countdown = 10 if impact == "critical" else 15

    _verifications[sos_id] = {
        "sos_id":       sos_id,
        "user_id":      str(current_user.id),
        "user_name":    current_user.name,
        "user_phone":   current_user.phone,
        "g_force":      g_force,
        "impact_class": impact,
        "state":        "pending",
        "created_at":   datetime.utcnow().isoformat(),
        "countdown_seconds": countdown,
        "audio_result": None,
        "voice_confirmed": None,
    }

    # Layer 5: place voice call for critical impacts
    if impact == "critical" and settings.TWILIO_SID:
        import threading
        t = threading.Thread(
            target=make_verification_call,
            args=(current_user.phone, sos_id, current_user.name),
            daemon=True
        )
        t.start()

    return {
        "sos_id":       sos_id,
        "impact_class": impact,
        "countdown_seconds": countdown,
        "message":      f"Verification started. {countdown}s to confirm safety.",
        "voice_call":   impact == "critical" and bool(settings.TWILIO_SID),
    }


@router.post("/im-ok")
async def user_confirmed_safe(
    sos_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Layer 2: User tapped 'I'm OK' button."""
    if sos_id not in _verifications:
        raise HTTPException(404, "Verification session not found")

    v = _verifications[sos_id]
    if v["user_id"] != str(current_user.id):
        raise HTTPException(403, "Not your SOS")

    v["state"] = "ok_by_user"
    v["resolved_at"] = datetime.utcnow().isoformat()

    # Cancel the SOS in DB
    await db.execute(
        update(EmergencyLog)
        .where(EmergencyLog.id == sos_id)
        .values(status="cancelled")
    )
    await db.commit()
    logger.info(f"SOS {sos_id} cancelled by user tap (I'm OK)")
    return {"message": "SOS cancelled. Stay safe!", "state": "ok_by_user"}


@router.post("/audio-analysis")
async def submit_audio_analysis(
    payload: AudioAnalysisPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Layer 4: Mobile sends mic analysis result."""
    if payload.sos_id not in _verifications:
        raise HTTPException(404, "Verification session not found")

    result = analyze_audio(payload)
    v = _verifications[payload.sos_id]
    v["audio_result"] = result

    if result["is_critical"] is False and result["confidence"] == "high":
        # Audio clearly shows user is fine — cancel
        v["state"] = "ok_by_user"
        await db.execute(
            update(EmergencyLog).where(EmergencyLog.id == payload.sos_id).values(status="cancelled")
        )
        await db.commit()
        logger.info(f"SOS {payload.sos_id} cancelled by audio analysis: {result['reason']}")
        return {"action": "cancelled", "reason": result["reason"]}

    if result["is_critical"] is True and result["confidence"] == "high":
        v["state"] = "audio_critical"
        logger.info(f"SOS {payload.sos_id} escalated by audio: {result['reason']}")
        return {"action": "escalate", "reason": result["reason"]}

    return {"action": "continue_countdown", "reason": result["reason"]}


@router.post("/voice-response/{sos_id}")
async def twilio_voice_callback(
    sos_id: str,
    Digits: str = "",   # Twilio sends keypress as form field
    db: AsyncSession = Depends(get_db),
):
    """
    Layer 5: Twilio calls this after user presses a key.
    Digits='1' → safe. Digits='2' → emergency.
    """
    from fastapi.responses import Response as FastAPIResponse

    if sos_id not in _verifications:
        twiml = '<Response><Say>Session expired. Goodbye.</Say></Response>'
        return FastAPIResponse(content=twiml, media_type="application/xml")

    v = _verifications[sos_id]

    if Digits == "1":
        v["state"] = "ok_by_voice"
        v["voice_confirmed"] = True
        await db.execute(
            update(EmergencyLog).where(EmergencyLog.id == sos_id).values(status="cancelled")
        )
        await db.commit()
        logger.info(f"SOS {sos_id} cancelled via voice keypress")
        twiml = '<Response><Say voice="alice">Great! Emergency cancelled. Drive safe!</Say></Response>'
    else:
        v["state"] = "escalated"
        v["voice_confirmed"] = False
        logger.info(f"SOS {sos_id} escalated via voice (pressed {Digits or 'nothing'})")
        twiml = '<Response><Say voice="alice">Understood. Dispatching emergency services now. Help is on the way.</Say></Response>'

    return FastAPIResponse(content=twiml, media_type="application/xml")


@router.get("/status/{sos_id}")
async def get_verification_status(sos_id: str, current_user: User = Depends(get_current_user)):
    """Frontend polls this to know if SOS was cancelled or escalated."""
    if sos_id not in _verifications:
        raise HTTPException(404, "Verification session not found")
    v = _verifications[sos_id]
    return {
        "sos_id":       v["sos_id"],
        "state":        v["state"],
        "state_label":  STATES.get(v["state"], v["state"]),
        "impact_class": v["impact_class"],
        "countdown_seconds": v["countdown_seconds"],
        "audio_result": v.get("audio_result"),
        "voice_confirmed": v.get("voice_confirmed"),
        "created_at":   v["created_at"],
    }


@router.post("/escalate/{sos_id}")
async def manual_escalate(
    sos_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Called by frontend when countdown expires with no response (Layer 3)."""
    if sos_id not in _verifications:
        raise HTTPException(404, "Verification session not found")
    v = _verifications[sos_id]
    if v["state"] in ("ok_by_user", "ok_by_voice"):
        return {"message": "Already cancelled — no escalation needed", "state": v["state"]}

    v["state"] = "escalated"
    v["escalated_at"] = datetime.utcnow().isoformat()
    logger.info(f"SOS {sos_id} escalated — no human response within {v['countdown_seconds']}s")
    return {"message": "Escalated to dispatch", "state": "escalated"}
