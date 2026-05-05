import asyncio, time, os
from celery import Celery
from twilio.rest import Client
from app.config import settings

celery_app = Celery("safepulse", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

def _get_twilio():
    return Client(settings.TWILIO_SID, settings.TWILIO_TOKEN)

def _get_sos_status(sos_id: str) -> str:
    """Sync DB check for Celery task (uses psycopg2 directly)."""
    import psycopg2
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT status FROM emergency_logs WHERE id = %s", (sos_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "unknown"

def _get_emergency_contacts(user_id: str) -> list:
    import psycopg2
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(url)
    cur = conn.cursor()
    cur.execute("SELECT emergency_contacts FROM medical_profiles WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else []

@celery_app.task
def start_sos_countdown(sos_id: str, user_id: str, lat: float, lon: float):
    time.sleep(15)  # 15-second cancellation window

    status = _get_sos_status(sos_id)
    if status == "cancelled":
        return {"result": "cancelled"}

    twilio = _get_twilio()
    maps_link = f"https://maps.google.com/?q={lat},{lon}"

    # Call emergency services
    twilio.calls.create(
        twiml='<Response><Say>Emergency SOS. Accident detected. Please respond immediately.</Say></Response>',
        to=settings.EMERGENCY_NUMBER,
        from_=settings.TWILIO_PHONE
    )

    # WhatsApp family alerts
    contacts = _get_emergency_contacts(user_id)
    for contact in (contacts or []):
        twilio.messages.create(
            body=f"SAFEPULSE ALERT: {contact.get('name','Your contact')} may have been in an accident.\nLocation: {maps_link}",
            from_=settings.TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{contact['phone']}"
        )

    return {"result": "alerts_sent"}

# For FastAPI BackgroundTasks (non-Celery path)
async def start_sos_countdown(sos_id: str, user_id: str, lat: float, lon: float):
    await asyncio.sleep(15)
    celery_app.send_task("app.tasks.start_sos_countdown", args=[sos_id, user_id, lat, lon])
