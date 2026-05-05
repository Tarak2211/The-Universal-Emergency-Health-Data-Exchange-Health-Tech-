"""
Smart Dispatch:
1. Find nearest available ambulance to incident
2. Find nearest hospital with emergency care (via OSM Overpass)
3. Dispatch — mark ambulance as en_route
4. Track movement, update ETA with traffic awareness
5. On phase advance, update ambulance status accordingly
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from app.database import get_db
from app.models import EmergencyLog, User
from app.auth import get_current_user, require_role
from app.config import settings
from app.routers.ambulance_router import (
    find_nearest_available, mark_ambulance_busy,
    mark_ambulance_available, update_fleet_position, _fleet
)
import math, httpx, logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dispatch", tags=["Dispatch"])
_store: dict[str, dict] = {}

PHASES = ["en_route","arrived_at_scene","patient_onboard","returning_to_hospital","completed"]

# ── Helpers ────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371
    dlat = math.radians(lat2-lat1); dlon = math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(max(0, a)))

async def find_nearest_hospital(lat: float, lon: float) -> dict:
    """Use OpenStreetMap Overpass API — worldwide, no API key needed.
    Searches within 10 km max — only nearby hospitals."""
    mirrors = [
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass-api.de/api/interpreter",
    ]
    for radius in [3000, 7000, 10000]:   # 3km → 7km → 10km max
        query = f"""[out:json][timeout:10];
(node["amenity"="hospital"]["emergency"="yes"](around:{radius},{lat},{lon});
 way["amenity"="hospital"]["emergency"="yes"](around:{radius},{lat},{lon});
 node["amenity"="hospital"](around:{radius},{lat},{lon});
 way["amenity"="hospital"](around:{radius},{lat},{lon}););
out center 5;"""
        for mirror in mirrors:
            try:
                async with httpx.AsyncClient(timeout=12) as client:
                    r = await client.get(mirror, params={"data": query})
                    if r.status_code != 200: continue
                    elements = r.json().get("elements", [])
                if not elements: continue
                best, best_dist = None, float("inf")
                for el in elements:
                    elat = el.get("lat") or el.get("center",{}).get("lat")
                    elon = el.get("lon") or el.get("center",{}).get("lon")
                    if elat is None: continue
                    d = haversine_km(lat, lon, elat, elon)
                    if d < best_dist:
                        best_dist = d
                        t = el.get("tags", {})
                        best = {
                            "name":        t.get("name") or t.get("name:en") or "Nearest Hospital",
                            "lat": elat,   "lon": elon,
                            "distance_km": round(best_dist, 2),
                            "emergency":   t.get("emergency","unknown"),
                            "phone":       t.get("phone") or t.get("contact:phone",""),
                            "address":     t.get("addr:full") or ", ".join(filter(None,[
                                               t.get("addr:street",""), t.get("addr:city",""), t.get("addr:state","")])),
                        }
                if best: return best
            except Exception as e:
                logger.warning(f"Overpass {mirror} r={radius}: {e}")
    # Absolute fallback — return incident coords so dispatch still works
    return {"name":"Nearest Hospital (lookup failed)","lat":lat,"lon":lon,"distance_km":0,"emergency":"unknown","phone":"","address":""}

async def eta_traffic(orig_lat, orig_lon, dest_lat, dest_lon) -> dict:
    key = settings.GOOGLE_MAPS_API_KEY
    if not key:
        km = haversine_km(orig_lat, orig_lon, dest_lat, dest_lon)
        return {"eta_minutes": round((km/40)*60, 1), "distance_km": round(km, 2), "traffic": "unknown"}
    try:
        params = {"origins":f"{orig_lat},{orig_lon}","destinations":f"{dest_lat},{dest_lon}",
                  "mode":"driving","departure_time":"now","traffic_model":"best_guess","key":key}
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get("https://maps.googleapis.com/maps/api/distancematrix/json", params=params)
        el = r.json()["rows"][0]["elements"][0]
        if el["status"] != "OK": raise ValueError()
        dur = el.get("duration_in_traffic", el["duration"])
        ratio = dur["value"] / max(el["duration"]["value"], 1)
        return {"eta_minutes": round(dur["value"]/60, 1),
                "distance_km": round(el["distance"]["value"]/1000, 2),
                "traffic": "heavy" if ratio>1.5 else "moderate" if ratio>1.15 else "clear"}
    except Exception as e:
        logger.warning(f"Google Maps ETA: {e}")
        km = haversine_km(orig_lat, orig_lon, dest_lat, dest_lon)
        return {"eta_minutes": round((km/40)*60, 1), "distance_km": round(km, 2), "traffic": "unknown"}

# ── Pydantic models ────────────────────────────────────────

class AutoDispatchRequest(BaseModel):
    sos_id: str
    # Optional overrides — if not provided, system auto-selects
    ambulance_id: str | None = None
    hospital_name: str | None = None
    hospital_lat: float | None = None
    hospital_lon: float | None = None

class ManualDispatchRequest(BaseModel):
    sos_id: str; ambulance_id: str; ambulance_name: str
    hospital_name: str = ""; start_lat: float; start_lon: float
    hospital_lat: float = 0.0; hospital_lon: float = 0.0

class AmbulanceUpdate(BaseModel):
    sos_id: str; current_lat: float; current_lon: float; speed_kmh: float = 40.0

class PhaseUpdate(BaseModel):
    sos_id: str; phase: str

# ── Routes ─────────────────────────────────────────────────

@router.get("/nearest-hospital")
async def nearest_hospital_endpoint(lat: float, lon: float, current_user: User = Depends(get_current_user)):
    return await find_nearest_hospital(lat, lon)


@router.post("/auto-assign")
async def auto_assign(
    req: AutoDispatchRequest,
    db: AsyncSession = Depends(get_db),
    operator: User = Depends(require_role("admin","doctor"))
):
    """
    Smart auto-dispatch:
    1. Finds nearest AVAILABLE ambulance to the incident
    2. Finds nearest hospital with emergency care
    3. Dispatches — no manual input needed
    """
    result = await db.execute(select(EmergencyLog).where(EmergencyLog.id == req.sos_id))
    log = result.scalar_one_or_none()
    if not log: raise HTTPException(404, "SOS event not found")

    inc_lat, inc_lon = log.latitude, log.longitude

    # Step 1: Find nearest available ambulance WITHIN 25 km only
    ranked = find_nearest_available(inc_lat, inc_lon)
    if not ranked: raise HTTPException(503, "No ambulances registered in fleet")

    if req.ambulance_id and req.ambulance_id in _fleet:
        chosen_amb = _fleet[req.ambulance_id]
        chosen_amb["distance_km"] = round(haversine_km(inc_lat, inc_lon, chosen_amb["lat"], chosen_amb["lon"]), 2)
        if chosen_amb["distance_km"] > 25:
            raise HTTPException(503, f"Specified ambulance is {chosen_amb['distance_km']} km away — too far. Only ambulances within 25 km can be dispatched.")
    else:
        available = [a for a in ranked if a["status"] == "available" and a["distance_km"] <= 25]
        if not available:
            # Check if any exist but are busy
            any_nearby = [a for a in ranked if a["distance_km"] <= 25]
            if any_nearby:
                raise HTTPException(503, "All nearby ambulances are currently busy. Please wait or try again shortly.")
            raise HTTPException(503, "No ambulances available within 25 km of this incident.")
        chosen_amb = available[0]

    # Step 2: Find nearest hospital
    if req.hospital_lat and req.hospital_lon:
        hosp = {"name": req.hospital_name or "Hospital", "lat": req.hospital_lat, "lon": req.hospital_lon,
                "distance_km": round(haversine_km(inc_lat, inc_lon, req.hospital_lat, req.hospital_lon), 2),
                "phone": "", "address": ""}
    else:
        hosp = await find_nearest_hospital(inc_lat, inc_lon)

    # Step 3: Calculate ETA from ambulance to incident
    eta_data = await eta_traffic(chosen_amb["lat"], chosen_amb["lon"], inc_lat, inc_lon)

    # Step 4: Mark ambulance as en_route
    mark_ambulance_busy(chosen_amb["id"])

    now = datetime.utcnow().isoformat()
    _store[req.sos_id] = {
        "sos_id":         req.sos_id,
        "ambulance_id":   chosen_amb["id"],
        "ambulance_name": chosen_amb["name"],
        "ambulance_type": chosen_amb.get("type","BLS"),
        "driver_name":    chosen_amb.get("driver",""),
        "driver_phone":   chosen_amb.get("phone",""),
        "amb_distance_km":chosen_amb["distance_km"],
        "hospital_name":  hosp["name"],
        "hospital_phone": hosp.get("phone",""),
        "hospital_address":hosp.get("address",""),
        "hospital_distance_km": hosp["distance_km"],
        "current_lat":    chosen_amb["lat"],
        "current_lon":    chosen_amb["lon"],
        "patient_lat":    inc_lat,
        "patient_lon":    inc_lon,
        "hospital_lat":   hosp["lat"],
        "hospital_lon":   hosp["lon"],
        "phase":          "en_route",
        "dispatched_at":  now,
        "phase_times":    {"en_route": now},
        "distance_km":    eta_data["distance_km"],
        "eta_minutes":    eta_data["eta_minutes"],
        "traffic":        eta_data["traffic"],
        "speed_kmh":      40.0,
        "trail":          [[chosen_amb["lat"], chosen_amb["lon"]]],
    }

    await db.execute(update(EmergencyLog).where(EmergencyLog.id == req.sos_id).values(status="responded"))
    await db.commit()

    return {
        "message": "Ambulance auto-dispatched",
        "ambulance": {
            "id": chosen_amb["id"], "name": chosen_amb["name"],
            "distance_from_incident_km": chosen_amb["distance_km"],
            "driver": chosen_amb.get("driver"), "phone": chosen_amb.get("phone"),
            "type": chosen_amb.get("type"),
        },
        "hospital": {
            "name": hosp["name"], "distance_km": hosp["distance_km"],
            "phone": hosp.get("phone"), "address": hosp.get("address"),
        },
        "eta_minutes": eta_data["eta_minutes"],
        "traffic": eta_data["traffic"],
    }


@router.post("/assign")
async def assign_ambulance(req: ManualDispatchRequest, db: AsyncSession = Depends(get_db),
                           operator: User = Depends(require_role("admin","doctor"))):
    """Manual dispatch — operator specifies ambulance and hospital."""
    result = await db.execute(select(EmergencyLog).where(EmergencyLog.id == req.sos_id))
    log = result.scalar_one_or_none()
    if not log: raise HTTPException(404, "SOS event not found")

    hosp_lat = req.hospital_lat or log.latitude
    hosp_lon = req.hospital_lon or log.longitude
    hosp_name = req.hospital_name
    if not req.hospital_lat:
        hosp = await find_nearest_hospital(log.latitude, log.longitude)
        hosp_lat, hosp_lon, hosp_name = hosp["lat"], hosp["lon"], hosp["name"]

    eta_data = await eta_traffic(req.start_lat, req.start_lon, log.latitude, log.longitude)
    mark_ambulance_busy(req.ambulance_id)

    now = datetime.utcnow().isoformat()
    _store[req.sos_id] = {
        "sos_id": req.sos_id, "ambulance_id": req.ambulance_id,
        "ambulance_name": req.ambulance_name, "hospital_name": hosp_name,
        "current_lat": req.start_lat, "current_lon": req.start_lon,
        "patient_lat": log.latitude, "patient_lon": log.longitude,
        "hospital_lat": hosp_lat, "hospital_lon": hosp_lon,
        "phase": "en_route", "dispatched_at": now, "phase_times": {"en_route": now},
        "distance_km": eta_data["distance_km"], "eta_minutes": eta_data["eta_minutes"],
        "traffic": eta_data["traffic"], "speed_kmh": 40.0,
        "trail": [[req.start_lat, req.start_lon]],
    }
    await db.execute(update(EmergencyLog).where(EmergencyLog.id == req.sos_id).values(status="responded"))
    await db.commit()
    return {"message": "Ambulance dispatched", "data": _store[req.sos_id]}


@router.post("/update-location")
async def update_location(req: AmbulanceUpdate):
    if req.sos_id not in _store: raise HTTPException(404, "No active dispatch")
    rec = _store[req.sos_id]
    rec["current_lat"] = req.current_lat; rec["current_lon"] = req.current_lon
    rec["speed_kmh"] = req.speed_kmh
    rec["trail"].append([req.current_lat, req.current_lon])
    if len(rec["trail"]) > 60: rec["trail"] = rec["trail"][-60:]

    # Update fleet position too
    update_fleet_position(rec["ambulance_id"], req.current_lat, req.current_lon)

    phase = rec["phase"]
    if phase in ("en_route","arrived_at_scene"):
        dlat, dlon = rec["patient_lat"], rec["patient_lon"]
    elif phase in ("patient_onboard","returning_to_hospital"):
        dlat, dlon = rec["hospital_lat"], rec["hospital_lon"]
    else:
        rec["distance_km"] = 0.0; rec["eta_minutes"] = 0.0; return rec

    eta_data = await eta_traffic(req.current_lat, req.current_lon, dlat, dlon)
    rec.update({"distance_km": eta_data["distance_km"], "eta_minutes": eta_data["eta_minutes"], "traffic": eta_data["traffic"]})

    dist = haversine_km(req.current_lat, req.current_lon, dlat, dlon)
    if dist < 0.05 and phase == "en_route":
        rec["phase"] = "arrived_at_scene"
        rec["phase_times"]["arrived_at_scene"] = datetime.utcnow().isoformat()
        update_fleet_position(rec["ambulance_id"], req.current_lat, req.current_lon)
        _fleet[rec["ambulance_id"]]["status"] = "at_scene"
    elif dist < 0.05 and phase == "returning_to_hospital":
        rec["phase"] = "completed"; rec["eta_minutes"] = 0.0
        rec["phase_times"]["completed"] = datetime.utcnow().isoformat()
        mark_ambulance_available(rec["ambulance_id"])
    return rec


@router.post("/advance-phase")
async def advance_phase(req: PhaseUpdate, operator: User = Depends(require_role("admin","doctor"))):
    if req.sos_id not in _store: raise HTTPException(404, "No active dispatch")
    if req.phase not in PHASES: raise HTTPException(400, "Invalid phase")
    rec = _store[req.sos_id]
    rec["phase"] = req.phase
    rec["phase_times"][req.phase] = datetime.utcnow().isoformat()

    # Update ambulance status to match phase
    amb_id = rec["ambulance_id"]
    phase_to_status = {
        "patient_onboard": "en_route",
        "returning_to_hospital": "returning",
        "completed": "available",
    }
    if req.phase in phase_to_status and amb_id in _fleet:
        _fleet[amb_id]["status"] = phase_to_status[req.phase]

    if req.phase == "returning_to_hospital":
        eta_data = await eta_traffic(rec["current_lat"], rec["current_lon"], rec["hospital_lat"], rec["hospital_lon"])
        rec.update(eta_data)
    return rec


@router.get("/status/{sos_id}")
async def get_dispatch_status(sos_id: str, current_user: User = Depends(get_current_user)):
    if sos_id not in _store: raise HTTPException(404, "No active dispatch")
    return _store[sos_id]


@router.get("/track/{sos_id}", response_class=HTMLResponse)
async def family_tracking_page(sos_id: str, db: AsyncSession = Depends(get_db)):
    rec = _store.get(sos_id, {})
    result = await db.execute(
        select(EmergencyLog, User.name).join(User, EmergencyLog.user_id==User.id).where(EmergencyLog.id==sos_id))
    row = result.first()
    if not row: return HTMLResponse("<h2>Tracking link not found.</h2>", status_code=404)
    log, patient_name = row
    amb_lat = rec.get("current_lat", log.latitude); amb_lon = rec.get("current_lon", log.longitude)
    phase = rec.get("phase","—"); eta = rec.get("eta_minutes","—")
    hospital = rec.get("hospital_name","—"); ambulance = rec.get("ambulance_name","—")
    traffic = rec.get("traffic","unknown")
    tc = {"clear":"#22c55e","moderate":"#f97316","heavy":"#ef4444"}.get(traffic,"#94a3b8")
    html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SafePulse Live Tracking</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:'Segoe UI',sans-serif;background:#0a0e1a;color:#e2e8f0}}
.hdr{{background:linear-gradient(135deg,#ef4444,#f97316);padding:16px 20px}}
.hdr h1{{font-size:1.2rem;font-weight:700;color:#fff}}.hdr p{{font-size:.8rem;color:rgba(255,255,255,.8);margin-top:2px}}
#map{{height:55vh;width:100%}}
.info{{padding:20px;display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.ic{{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:14px}}
.ic .v{{font-size:1.3rem;font-weight:800;margin-bottom:4px}}.ic .l{{font-size:.72rem;color:#718096;text-transform:uppercase}}
.phase{{margin:0 20px 20px;padding:14px 16px;background:rgba(249,115,22,.1);border:1px solid rgba(249,115,22,.25);border-radius:10px;font-size:.9rem;font-weight:600;color:#fdba74}}
.note{{text-align:center;padding:12px;font-size:.75rem;color:#718096}}</style></head><body>
<div class="hdr"><h1>🚨 SafePulse Live Tracking</h1><p>Patient: {patient_name} · {log.severity.upper()}</p></div>
<div id="map"></div>
<div class="phase">🚑 {phase.replace('_',' ').title()}</div>
<div class="info">
  <div class="ic"><div class="v" style="color:#f97316">{eta} min</div><div class="l">ETA</div></div>
  <div class="ic"><div class="v" style="color:{tc}">{traffic.title()}</div><div class="l">Traffic</div></div>
  <div class="ic"><div class="v" style="color:#93c5fd;font-size:1rem">{ambulance}</div><div class="l">Ambulance</div></div>
  <div class="ic"><div class="v" style="color:#86efac;font-size:.9rem">{hospital}</div><div class="l">Hospital</div></div>
</div>
<div class="note">Auto-refreshes every 10 seconds</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const map=L.map('map').setView([{amb_lat},{amb_lon}],14);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png',{{attribution:'© CARTO',subdomains:'abcd'}}).addTo(map);
function icon(e,s){{return L.divIcon({{html:`<div style="font-size:${{s}}px;filter:drop-shadow(0 2px 6px rgba(0,0,0,.6))">${{e}}</div>`,className:'',iconAnchor:[s/2,s/2]}})}}
L.marker([{log.latitude},{log.longitude}],{{icon:icon('🔴',30)}}).addTo(map).bindPopup('<b>Patient</b>').openPopup();
L.marker([{amb_lat},{amb_lon}],{{icon:icon('🚑',34)}}).addTo(map).bindPopup('<b>{ambulance}</b>');
setTimeout(()=>location.reload(),10000);
</script></body></html>"""
    return HTMLResponse(html)


@router.get("/incidents")
async def get_all_incidents(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(EmergencyLog, User.name).join(User, EmergencyLog.user_id==User.id)
        .order_by(EmergencyLog.triggered_at.desc()).limit(100))
    out = []
    for log, uname in result.all():
        if current_user.role == "patient" and str(log.user_id) != str(current_user.id): continue
        rec = _store.get(str(log.id), {})
        out.append({
            "id": str(log.id), "patient_name": uname, "patient_id": str(log.user_id),
            "severity": log.severity, "status": log.status,
            "triggered_at": log.triggered_at.isoformat() if log.triggered_at else None,
            "latitude": log.latitude, "longitude": log.longitude, "g_force": log.g_force_peak,
            "ambulance": rec.get("ambulance_name"), "ambulance_id": rec.get("ambulance_id"),
            "ambulance_type": rec.get("ambulance_type"), "driver_name": rec.get("driver_name"),
            "driver_phone": rec.get("driver_phone"),
            "hospital_name": rec.get("hospital_name"), "hospital_phone": rec.get("hospital_phone"),
            "hospital_address": rec.get("hospital_address"),
            "amb_distance_km": rec.get("amb_distance_km"),
            "hospital_distance_km": rec.get("hospital_distance_km"),
            "phase": rec.get("phase"), "phase_times": rec.get("phase_times", {}),
            "eta_minutes": rec.get("eta_minutes"), "distance_km": rec.get("distance_km"),
            "traffic": rec.get("traffic","unknown"),
            "amb_lat": rec.get("current_lat"), "amb_lon": rec.get("current_lon"),
            "hospital_lat": rec.get("hospital_lat"), "hospital_lon": rec.get("hospital_lon"),
            "trail": rec.get("trail", []),
            "tracking_url": f"{settings.APP_BASE_URL}/dispatch/track/{log.id}",
        })
    return out
