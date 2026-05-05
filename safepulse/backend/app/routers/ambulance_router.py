"""
Ambulance Fleet Registry
- Thread-safe in-memory store with asyncio.Lock
- For production at scale: replace _fleet with Redis hash
"""
import math
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from app.auth import get_current_user, require_role
from app.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ambulances", tags=["Ambulance Fleet"])

# ── Fleet store + lock ────────────────────────────────────
_fleet: dict[str, dict] = {
    "AMB-001": {"id":"AMB-001","name":"Ahmedabad 108 Unit 1","lat":23.0395,"lon":72.5290,"status":"available","driver":"Ramesh Patel",  "phone":"9800000001","type":"ALS"},
    "AMB-002": {"id":"AMB-002","name":"Ahmedabad 108 Unit 2","lat":23.0469,"lon":72.6693,"status":"available","driver":"Sunil Shah",    "phone":"9800000002","type":"BLS"},
    "AMB-003": {"id":"AMB-003","name":"EMRI Unit 3",          "lat":23.0600,"lon":72.5800,"status":"available","driver":"Kiran Desai",  "phone":"9800000003","type":"ALS"},
    "AMB-004": {"id":"AMB-004","name":"EMRI Unit 4",          "lat":23.0153,"lon":72.5800,"status":"available","driver":"Deepak Joshi", "phone":"9800000004","type":"BLS"},
    "AMB-005": {"id":"AMB-005","name":"Civil Hospital Unit 5","lat":23.0258,"lon":72.5873,"status":"available","driver":"Amit Kumar",   "phone":"9800000005","type":"ALS"},
    "AMB-006": {"id":"AMB-006","name":"Bopal Community Unit", "lat":23.0300,"lon":72.5050,"status":"available","driver":"Vijay Nair",   "phone":"9800000006","type":"BLS"},
}
_fleet_lock = asyncio.Lock()

VALID_STATUSES = {"available", "en_route", "at_scene", "returning", "offline"}

# ── Helpers ───────────────────────────────────────────────
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(max(0.0, a)))

def find_nearest_available(inc_lat: float, inc_lon: float) -> list[dict]:
    scored = []
    for amb in _fleet.values():
        dist = haversine_km(inc_lat, inc_lon, amb["lat"], amb["lon"])
        scored.append({**amb, "distance_km": round(dist, 2)})
    available = sorted([a for a in scored if a["status"] == "available"],  key=lambda x: x["distance_km"])
    busy      = sorted([a for a in scored if a["status"] not in ("available","offline")], key=lambda x: x["distance_km"])
    offline   = [a for a in scored if a["status"] == "offline"]
    return available + busy + offline

def mark_ambulance_busy(amb_id: str):
    if amb_id in _fleet:
        _fleet[amb_id]["status"] = "en_route"
        logger.info(f"Ambulance {amb_id} marked en_route")

def mark_ambulance_available(amb_id: str):
    if amb_id in _fleet:
        _fleet[amb_id]["status"] = "available"
        logger.info(f"Ambulance {amb_id} returned to available")

def update_fleet_position(amb_id: str, lat: float, lon: float):
    if amb_id in _fleet:
        _fleet[amb_id]["lat"] = lat
        _fleet[amb_id]["lon"] = lon

# ── Pydantic models ───────────────────────────────────────
class AmbulanceLocationUpdate(BaseModel):
    lat: float
    lon: float
    status: str | None = None

    @field_validator("lat")
    @classmethod
    def lat_ok(cls, v):
        if not (-90 <= v <= 90): raise ValueError("Invalid latitude")
        return round(v, 8)

    @field_validator("lon")
    @classmethod
    def lon_ok(cls, v):
        if not (-180 <= v <= 180): raise ValueError("Invalid longitude")
        return round(v, 8)

class RegisterAmbulance(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    driver: str = ""
    phone: str = ""
    type: str = "BLS"

    @field_validator("type")
    @classmethod
    def type_ok(cls, v):
        if v not in ("ALS","BLS"): raise ValueError("Type must be ALS or BLS")
        return v

# ── Routes ────────────────────────────────────────────────
@router.get("/fleet")
async def get_fleet(current_user: User = Depends(get_current_user)):
    return list(_fleet.values())

@router.get("/nearest")
async def get_nearest(lat: float, lon: float, current_user: User = Depends(get_current_user)):
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Invalid coordinates")
    return find_nearest_available(lat, lon)

@router.post("/register", status_code=201)
async def register_ambulance(req: RegisterAmbulance, operator: User = Depends(require_role("admin"))):
    async with _fleet_lock:
        if req.id in _fleet:
            raise HTTPException(status_code=409, detail=f"Ambulance {req.id} already registered")
        _fleet[req.id] = {
            "id": req.id, "name": req.name, "lat": req.lat, "lon": req.lon,
            "status": "available", "driver": req.driver, "phone": req.phone, "type": req.type,
        }
    logger.info(f"Ambulance registered: {req.id} by {operator.id}")
    return {"message": f"Ambulance {req.id} registered"}

@router.patch("/{amb_id}/location")
async def update_location(amb_id: str, update: AmbulanceLocationUpdate,
                          current_user: User = Depends(get_current_user)):
    if amb_id not in _fleet:
        raise HTTPException(status_code=404, detail="Ambulance not found")
    async with _fleet_lock:
        _fleet[amb_id]["lat"] = update.lat
        _fleet[amb_id]["lon"] = update.lon
        if update.status:
            if update.status not in VALID_STATUSES:
                raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {VALID_STATUSES}")
            _fleet[amb_id]["status"] = update.status
    return _fleet[amb_id]

@router.patch("/{amb_id}/status")
async def update_status(amb_id: str, status: str,
                        operator: User = Depends(require_role("admin","doctor"))):
    if amb_id not in _fleet:
        raise HTTPException(status_code=404, detail="Ambulance not found")
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {VALID_STATUSES}")
    async with _fleet_lock:
        _fleet[amb_id]["status"] = status
    logger.info(f"Ambulance {amb_id} status set to {status} by {operator.id}")
    return _fleet[amb_id]
