# SafePulse — Emergency Response System

> A full-stack, dual-platform emergency response system built with Python (FastAPI) + Flutter (Mobile) + Vanilla JS (Web Dashboard). Designed for real-world accident detection, smart ambulance dispatch, live tracking, and digital health records.

---

## What Is SafePulse?

SafePulse is an end-to-end emergency health platform with three parts:

| Part | Technology | Purpose |
|---|---|---|
| Backend API | Python · FastAPI · SQLite | All business logic, data, dispatch engine |
| Web Dashboard | Vanilla HTML/CSS/JS · Leaflet.js | Control room, doctors, admin analytics |
| Mobile App | Flutter · Dart | Patient-side accident detection, SOS trigger |

---

## Project Structure

```
safepulse/
├── backend/                        # Python FastAPI backend
│   ├── app/
│   │   ├── main.py                 # App entry point, router registration, CORS
│   │   ├── config.py               # All environment settings (DB, Twilio, etc.)
│   │   ├── database.py             # SQLite async engine, session factory, init_db
│   │   ├── models.py               # SQLAlchemy ORM models
│   │   ├── auth.py                 # JWT auth, bcrypt password hashing
│   │   ├── tasks.py                # Celery background tasks (SOS alerts)
│   │   ├── routers/
│   │   │   ├── auth_router.py      # POST /auth/register, POST /auth/login
│   │   │   ├── sos_router.py       # SOS trigger/cancel, medical ID, logs
│   │   │   ├── medical_router.py   # Medical profiles, prescriptions, records
│   │   │   ├── dispatch_router.py  # Smart dispatch, live tracking, family tracking
│   │   │   ├── ambulance_router.py # Fleet registry, nearest ambulance ranking
│   │   │   ├── analytics_router.py # Hotspot reports, response time charts
│   │   │   └── payment_router.py   # Razorpay UPI order creation + verification
│   │   ├── analytics/
│   │   │   └── hotspots.py         # Pandas/Seaborn accident heatmap generation
│   │   └── sensor/
│   │       └── accident_detector.py # G-force algorithm, false-alarm filtering
│   ├── seed_ahmedabad.py           # Ahmedabad test data seeder
│   ├── seed.py                     # Original Mumbai seeder (replaced)
│   ├── requirements.txt            # All Python dependencies
│   ├── Dockerfile                  # Docker image for backend
│   ├── .env                        # Active environment variables
│   └── .env.example                # Template for environment setup
│
├── web/
│   └── index.html                  # Complete single-file web dashboard
│
├── mobile/
│   ├── pubspec.yaml                # Flutter dependencies
│   └── lib/
│       ├── config.dart             # API base URL config
│       ├── services/
│       │   ├── sensor_service.dart # Accelerometer reading + accident detection
│       │   └── sos_service.dart    # SOS trigger/cancel API calls
│       └── screens/
│           ├── sos_countdown_screen.dart  # 15-second cancel countdown UI
│           └── medical_id_screen.dart     # Lock-screen medical profile display
│
└── docker-compose.yml              # PostgreSQL + Redis + API + Celery (production)
```

---

## Database Schema

### users
| Column | Type | Description |
|---|---|---|
| id | UUID | Primary key |
| name | String | Full name |
| phone | String | Unique login identifier |
| hashed_password | String | bcrypt hash |
| role | String | `patient` / `doctor` / `admin` |
| abha_id | String | Government health ID (optional) |
| created_at | Timestamp | Registration time |

### medical_profiles
| Column | Type | Description |
|---|---|---|
| user_id | FK → users | One profile per patient |
| blood_type | String | e.g. B+, O- |
| allergies | JSON Text | List of allergy strings |
| conditions | JSON Text | List of medical conditions |
| medications | JSON Text | Current medications |
| emergency_contacts | JSON Text | [{name, phone, relation}] |

### emergency_logs
| Column | Type | Description |
|---|---|---|
| user_id | FK → users | Who triggered the SOS |
| triggered_at | Timestamp | When it happened |
| latitude / longitude | Float | GPS coordinates of accident |
| g_force_peak | Float | Peak G-force reading |
| severity | String | `low` / `moderate` / `severe` |
| status | String | `triggered` / `cancelled` / `responded` / `closed` |

### medical_records
| Column | Type | Description |
|---|---|---|
| patient_id | FK → users | Patient |
| doctor_id | FK → users | Issuing doctor |
| record_type | String | `prescription` / `report` / `history` |
| content | JSON Text | Diagnosis, medicines, notes |
| issued_at | Timestamp | Issue date |

### payments
| Column | Type | Description |
|---|---|---|
| user_id | FK → users | Payer |
| amount | Float | Amount in INR |
| razorpay_order_id | String | Razorpay reference |
| status | String | `pending` / `success` / `failed` |

---

## All API Endpoints

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register new user (patient/doctor/admin) |
| POST | `/auth/login` | Login, returns JWT token |

### SOS
| Method | Endpoint | Description |
|---|---|---|
| POST | `/sos/trigger` | Trigger SOS — auto-computes severity from G-force |
| POST | `/sos/{id}/cancel` | Cancel within 15-second window |
| GET | `/sos/medical-id` | Get logged-in user's emergency medical profile |
| GET | `/sos/logs` | Get user's SOS history |

### Medical
| Method | Endpoint | Description |
|---|---|---|
| PUT | `/medical/profile` | Update blood type, allergies, conditions, medications, contacts |
| POST | `/medical/prescription` | Doctor issues digital prescription |
| GET | `/medical/records/{patient_id}` | Get all records for a patient |
| GET | `/medical/patient-summary/{patient_id}` | Full health summary for hospital on arrival |
| GET | `/medical/abha/{abha_id}/records` | Fetch ABHA government health records |

### Dispatch
| Method | Endpoint | Description |
|---|---|---|
| POST | `/dispatch/auto-assign` | Smart dispatch — auto-picks nearest available ambulance + hospital |
| POST | `/dispatch/assign` | Manual dispatch with explicit ambulance and hospital |
| POST | `/dispatch/update-location` | Update ambulance GPS position |
| POST | `/dispatch/advance-phase` | Manually advance lifecycle phase |
| GET | `/dispatch/status/{sos_id}` | Get live dispatch status |
| GET | `/dispatch/nearest-hospital` | Find nearest hospital via OpenStreetMap |
| GET | `/dispatch/track/{sos_id}` | Public family tracking page (no login needed) |
| GET | `/dispatch/incidents` | All incidents with dispatch data |

### Ambulance Fleet
| Method | Endpoint | Description |
|---|---|---|
| GET | `/ambulances/fleet` | All registered ambulances with status |
| GET | `/ambulances/nearest?lat=&lon=` | Ranked list by distance — available first |
| POST | `/ambulances/register` | Register new ambulance (admin only) |
| PATCH | `/ambulances/{id}/location` | Update ambulance GPS |
| PATCH | `/ambulances/{id}/status` | Update ambulance status |

### Analytics
| Method | Endpoint | Description |
|---|---|---|
| GET | `/analytics/hotspots` | Accident heatmap + top danger zones (admin) |
| GET | `/analytics/response-times` | Average response time chart (admin) |

### Payments
| Method | Endpoint | Description |
|---|---|---|
| POST | `/payments/create-order` | Create Razorpay UPI order |
| POST | `/payments/verify` | Verify payment signature server-side |

---

## Features — Detailed Explanation

### 1. Accident Detection Algorithm
**File:** `backend/app/sensor/accident_detector.py`
**Used when:** Mobile app sends accelerometer readings to the backend for validation.

Two-phase detection:
- Phase 1 — detects a G-force spike above 4.0g (potential crash)
- Phase 2 — checks the 3 seconds after impact for stillness (victim incapacitated)
- False alarm filter — a dropped phone spikes then shows movement as it's picked up; a crash victim stays still

G-force thresholds:
- `< 3.5g` → Low severity
- `3.5–7.0g` → Moderate severity
- `≥ 7.0g` → **Critical/Severe** — triggers high-priority hospital alert automatically

### 2. SOS Trigger & 15-Second Countdown
**File:** `backend/app/routers/sos_router.py`
**Used when:** Accident is detected on the mobile app or manually triggered from the dashboard.

- Severity is auto-computed from G-force — no manual selection needed
- A 15-second cancellation window is given (in case of false alarm)
- If not cancelled, family contacts are alerted via WhatsApp/SMS (Twilio)
- A public family tracking link is generated and included in the alert

### 3. Smart Auto-Dispatch
**File:** `backend/app/routers/dispatch_router.py` + `ambulance_router.py`
**Used when:** Admin/doctor clicks "Assign Ambulance" in the Dispatch Center.

Logic:
1. Fetches all ambulances from the fleet registry
2. Ranks them by distance to the accident location using Haversine formula
3. Picks the **nearest available** ambulance (status = `available`)
4. If nearest is busy (`en_route`, `at_scene`, `returning`), picks the next closest available
5. Simultaneously finds the nearest hospital via OpenStreetMap Overpass API
6. Dispatches — marks ambulance as `en_route`, stores full dispatch record

### 4. Ambulance Fleet Registry
**File:** `backend/app/routers/ambulance_router.py`
**Used when:** Dispatch Center loads, or when auto-dispatch needs to rank ambulances.

6 pre-registered Ahmedabad ambulances:
- EMRI Unit 4 — Makarba area (1.19 km from Bopal)
- Civil Hospital Unit 5 — Prahlad Nagar (1.67 km)
- EMRI Unit 3 — Satellite Road (4.26 km)
- Ahmedabad 108 Unit 1 — Ghuma (4.73 km)
- Bopal Community Unit — Bopal Chokdi (6.85 km)
- Ahmedabad 108 Unit 2 — Naranpura (10.38 km)

Status lifecycle: `available` → `en_route` → `at_scene` → `returning` → `available`

### 5. Ambulance Phase Tracking
**File:** `backend/app/routers/dispatch_router.py`
**Used when:** Ambulance is dispatched and moving.

5 phases with timestamps:
1. **En Route** — ambulance moving toward patient
2. **Arrived at Scene** — auto-triggers when within 50m of patient
3. **Patient On Board** — operator manually marks via dashboard button
4. **Returning to Hospital** — operator marks; ETA recalculates to hospital
5. **Completed** — auto-triggers on hospital arrival; ambulance returns to `available`

### 6. Nearest Hospital via OpenStreetMap
**File:** `backend/app/routers/dispatch_router.py` → `find_nearest_hospital()`
**Used when:** Auto-dispatch runs, or operator opens the dispatch modal.

- Uses OpenStreetMap Overpass API — free, no API key, works worldwide
- Searches with expanding radius: 5km → 15km → 30km
- Tries 3 mirror servers for reliability
- Prioritises hospitals tagged with `emergency=yes`
- Returns name, coordinates, distance, phone, address

Example — Bopal Vakil Saheb Bridge (23.0225, 72.5714):
→ Returns **Saviour Annexe Hospital, 1.6 km away**

### 7. Traffic-Aware ETA
**File:** `dispatch_router.py` → `eta_traffic()`
**Used when:** Ambulance location is updated, or dispatch is assigned.

- If `GOOGLE_MAPS_API_KEY` is set in `.env` → uses Google Distance Matrix API with real-time traffic
- Without the key → falls back to Haversine distance ÷ 40 km/h
- Traffic condition shown as: 🟢 Clear / 🟠 Moderate / 🔴 Heavy

### 8. Live Map — Dispatch Center
**File:** `web/index.html` (Leaflet.js)
**Used when:** Admin/doctor opens the Dispatch Center tab.

Map shows:
- 🔴 Patient location markers
- 🚑 Ambulance markers (move in real-time every 2.5 seconds)
- 🏥 Hospital destination markers
- Orange breadcrumb trail of ambulance path
- Blue dashed line to current destination
- Fleet ambulances with status-colored dots (🟢🟠🟡🔵⚫)

### 9. Family Tracking Link
**File:** `dispatch_router.py` → `/dispatch/track/{sos_id}`
**Used when:** SOS is triggered — link is sent to family via WhatsApp/SMS.

- Public page, no login required
- Shows live ambulance position on map
- Displays ETA, traffic condition, ambulance name, hospital name
- Auto-refreshes every 10 seconds
- Works on any device (mobile-responsive)

### 10. Digital Health Records
**File:** `backend/app/routers/medical_router.py`
**Used when:** Doctor clicks "View Patient Health Record" in Dispatch Center.

Shows:
- Blood type, allergies, conditions, medications
- All past prescriptions with diagnosis and medicines
- ABHA government health ID linkage
- Emergency contacts

### 11. Bystander Voice Instructions
**File:** `web/index.html` (Web Speech API)
**Used when:** Someone is near an accident and needs guidance before the ambulance arrives.

5 audio instructions (browser text-to-speech):
- Lay Patient Flat
- Control Bleeding
- CPR Instructions
- Check Breathing
- Keep Patient Calm

### 12. Python Analytics — Accident Hotspots
**File:** `backend/app/analytics/hotspots.py`
**Used when:** Admin opens the Analytics section.

- Reads all emergency logs from the database
- Bins GPS coordinates into 500m × 500m grid cells
- Generates a Seaborn heatmap of accident density
- Bar chart of top 10 danger zones with average G-force and response time
- Saved as PNG, served at `/static/reports/hotspots.png`

### 13. UPI Payment Integration
**File:** `backend/app/routers/payment_router.py`
**Used when:** Patient pays hospital or pharmacy bill via the web dashboard.

- Creates Razorpay order server-side
- Frontend opens Razorpay checkout with UPI option
- Payment signature verified server-side using HMAC-SHA256 (never trust client)

### 14. Tag-Input Medical Profile
**File:** `web/index.html`
**Used when:** Patient updates their medical profile.

- No JSON brackets needed — type a word, press Enter or comma → becomes a pill tag
- Allergies (red tags), Conditions (orange), Medications (green)
- Emergency contacts as structured Name / Phone / Relation rows

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.13 |
| Web framework | FastAPI (async) |
| Database (dev) | SQLite via aiosqlite |
| Database (prod) | PostgreSQL + PostGIS |
| ORM | SQLAlchemy 2.0 (async) |
| Auth | JWT (python-jose) + bcrypt |
| Background tasks | Celery + Redis |
| SMS / WhatsApp | Twilio |
| Payments | Razorpay UPI |
| Analytics | Pandas + Matplotlib + Seaborn |
| Maps (backend) | OpenStreetMap Overpass API |
| Maps (frontend) | Leaflet.js + CartoDB Voyager tiles |
| Traffic ETA | Google Maps Distance Matrix API (optional) |
| Mobile | Flutter + Dart |
| Web dashboard | Vanilla HTML/CSS/JS (single file) |
| Voice instructions | Web Speech API (browser built-in) |
| Containerisation | Docker + Docker Compose |

---

## Environment Variables (.env)

```env
# Database
DATABASE_URL=sqlite+aiosqlite:///./safepulse.db

# Security
SECRET_KEY=your-secret-key
FERNET_KEY=your-fernet-key          # generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Twilio (SMS + WhatsApp alerts)
TWILIO_SID=ACxxxxxxxxxxxxxxxx
TWILIO_TOKEN=your_auth_token
TWILIO_PHONE=+1xxxxxxxxxx
EMERGENCY_NUMBER=112
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

# Razorpay (UPI payments)
RAZORPAY_KEY=rzp_test_xxxxxxxxxx
RAZORPAY_SECRET=your_secret

# Google Maps (optional — for traffic-aware ETA)
GOOGLE_MAPS_API_KEY=AIza...

# App base URL (for family tracking links in SMS)
APP_BASE_URL=http://localhost:8000

# ABHA Government Health API
ABHA_BASE_URL=https://dev.abdm.gov.in/gateway
```

---

## Step-by-Step Setup

### Prerequisites
- Python 3.11+ installed
- Windows / macOS / Linux

### Step 1 — Clone / open the project
```
The project is already at:
safepulse/
```

### Step 2 — Create Python virtual environment
```bash
cd safepulse/backend
python -m venv venv
```

### Step 3 — Activate the virtual environment
```bash
# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### Step 4 — Install dependencies
```bash
pip install fastapi "uvicorn[standard]" sqlalchemy asyncpg alembic aiosqlite \
  pydantic pydantic-settings python-jose passlib bcrypt celery redis \
  twilio httpx razorpay pandas matplotlib seaborn cryptography \
  slowapi python-multipart psycopg2-binary geoalchemy2
```

### Step 5 — Set up environment file
```bash
copy .env.example .env      # Windows
cp .env.example .env        # macOS/Linux
```
Then generate a Fernet key and paste it into `.env`:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Step 6 — Start the API server
```bash
# From safepulse/backend/
venv/Scripts/uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Tables are created automatically on first startup.

### Step 7 — Seed Ahmedabad test data
```bash
# In a new terminal, from the project root
safepulse/backend/venv/Scripts/python safepulse/backend/seed_ahmedabad.py
```

### Step 8 — Open the web dashboard
Open `safepulse/web/index.html` directly in your browser.

Login credentials after seeding:
```
Admin   → 9999999999 / Test@1234
Doctor  → 9876543210 / Doctor@123
Patient → 9123456780 / Patient@123
Patient → 9234567801 / Patient@123
Patient → 9345678012 / Patient@123
```

### Step 9 — API documentation
Visit `http://localhost:8000/docs` for the full interactive Swagger UI.

---

## Dashboard Sections

| Section | Who Uses It | What It Does |
|---|---|---|
| Overview | All roles | Live stats — total SOS, avg response time, active alerts, recent activity |
| SOS Logs | Patient | Table of own emergency history with severity/status badges |
| Medical ID | Patient | Read-only view of emergency medical profile for first responders |
| Update Profile | Patient | Tag-input form for blood type, allergies, conditions, medications, contacts |
| Issue Prescription | Doctor/Admin | Digital prescription form linked to patient UUID |
| Trigger SOS | All | Test SOS with auto-severity preview, voice bystander instructions |
| Dispatch Center | Admin/Doctor | Live map, fleet status, smart auto-dispatch, phase tracking, health records |

---

## Ambulance Fleet (Pre-seeded for Ahmedabad)

| Unit | Location | Type | Distance from Bopal |
|---|---|---|---|
| EMRI Unit 4 | Makarba | ALS | 1.19 km |
| Civil Hospital Unit 5 | Prahlad Nagar | ALS | 1.67 km |
| EMRI Unit 3 | Satellite Road | ALS | 4.26 km |
| Ahmedabad 108 Unit 1 | Ghuma | ALS | 4.73 km |
| Bopal Community Unit | Bopal Chokdi | BLS | 6.85 km |
| Ahmedabad 108 Unit 2 | Naranpura | BLS | 10.38 km |

ALS = Advanced Life Support · BLS = Basic Life Support

---

## How Smart Dispatch Works (Step by Step)

1. Accident detected → SOS triggered at GPS coordinates
2. Admin opens Dispatch Center → clicks "Assign" on the incident
3. System simultaneously:
   - Calls `/ambulances/nearest?lat=&lon=` → ranks all 6 ambulances by distance
   - Calls `/dispatch/nearest-hospital?lat=&lon=` → queries OpenStreetMap for nearest hospital
4. Modal shows: nearest available ambulance + nearest hospital + full ranked list
5. Admin clicks "Dispatch Now" → `/dispatch/auto-assign` is called
6. Backend marks ambulance as `en_route`, stores dispatch record
7. Ambulance marker appears on map and moves every 2.5 seconds
8. ETA updates live; phase stepper advances automatically
9. On arrival at scene → phase auto-advances to `Arrived at Scene`
10. Operator clicks "Mark Patient On Board" → phase advances
11. Operator clicks "Start Return to Hospital" → ambulance route flips to hospital
12. On hospital arrival → phase = `Completed`, ambulance returns to `available`

---

## Security Notes

- All passwords hashed with bcrypt (never stored plain)
- JWT tokens expire after 60 minutes
- Medical records are role-gated — patients only see their own data
- Payment signatures verified server-side with HMAC-SHA256
- ABHA tokens stored encrypted at rest with Fernet symmetric encryption
- CORS configured (restrict origins in production)
- Rate limiting on SOS endpoint via slowapi

---

## Production Deployment (Docker)

```bash
cd safepulse
docker-compose up --build
```

This starts:
- PostgreSQL + PostGIS database
- Redis (for Celery task queue)
- FastAPI application server
- Celery worker (background SOS alerts)

For production, replace SQLite URL in `.env` with:
```
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/safepulse
```

---

## Mobile App (Flutter)

**File:** `safepulse/mobile/`

| File | Purpose |
|---|---|
| `sensor_service.dart` | Reads accelerometer every tick, runs two-phase crash detection |
| `sos_service.dart` | Calls `/sos/trigger` and `/sos/{id}/cancel` |
| `sos_countdown_screen.dart` | Red full-screen countdown with "I'm OK — Cancel" button |
| `medical_id_screen.dart` | Lock-screen display of blood type, allergies, emergency contacts |

To run:
```bash
cd safepulse/mobile
flutter pub get
flutter run
```

---

*SafePulse — Built to save lives, one second at a time.*
