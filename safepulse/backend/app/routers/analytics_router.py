from fastapi import APIRouter, Depends
from app.auth import require_role
from app.analytics.hotspots import generate_hotspot_report
from app.models import User

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/hotspots")
async def hotspots(admin: User = Depends(require_role("admin"))):
    report = generate_hotspot_report()
    return report

@router.get("/response-times")
async def response_times(admin: User = Depends(require_role("admin"))):
    from app.analytics.hotspots import generate_response_time_report
    return generate_response_time_report()
