"""
SafePulse — Ahmedabad Seed Data
Run: python seed_ahmedabad.py
"""
import requests, json, base64, time, random

BASE = "http://localhost:8000"

# ── Users ──────────────────────────────────────────────────
USERS = [
    {"name": "Aryan Admin",        "phone": "9999999999", "password": "Test@1234",   "role": "admin"},
    {"name": "Dr. Priya Sharma",   "phone": "9876543210", "password": "Doctor@123",  "role": "doctor"},
    {"name": "Rahul Verma",        "phone": "9123456780", "password": "Patient@123", "role": "patient"},
    {"name": "Sneha Patel",        "phone": "9234567801", "password": "Patient@123", "role": "patient"},
    {"name": "Arjun Mehta",        "phone": "9345678012", "password": "Patient@123", "role": "patient"},
]

# ── Ahmedabad accident locations ───────────────────────────
# Real Ahmedabad landmarks / accident-prone areas
LOCATIONS = [
    (23.0225, 72.5714, "Bopal — Vakil Saheb Bridge"),
    (23.0300, 72.5050, "Bopal Chokdi"),
    (23.0395, 72.5290, "Ghuma Circle"),
    (23.0600, 72.5800, "Satellite Road"),
    (23.0732, 72.5170, "Sarkhej–Gandhinagar Highway"),
    (23.0469, 72.6693, "Naranpura"),
    (23.0258, 72.5873, "Prahlad Nagar"),
    (23.0153, 72.5800, "Makarba"),
    (23.0500, 72.6300, "Navrangpura"),
    (22.9950, 72.5990, "Isanpur"),
]

# ── Medical profiles ───────────────────────────────────────
PROFILES = {
    "9123456780": {
        "blood_type": "B+",
        "allergies": ["Penicillin", "Sulfa drugs"],
        "conditions": ["Type 2 Diabetes", "Hypertension"],
        "medications": ["Metformin 500mg", "Lisinopril 10mg", "Aspirin 75mg"],
        "emergency_contacts": [
            {"name": "Meena Verma",  "phone": "+91 9000000001", "relation": "Spouse"},
            {"name": "Suresh Verma", "phone": "+91 9000000002", "relation": "Father"},
        ]
    },
    "9234567801": {
        "blood_type": "O+",
        "allergies": ["Latex", "Ibuprofen"],
        "conditions": ["Asthma", "Anxiety Disorder"],
        "medications": ["Salbutamol Inhaler", "Montelukast 10mg"],
        "emergency_contacts": [
            {"name": "Raj Patel", "phone": "+91 9000000003", "relation": "Husband"},
        ]
    },
    "9345678012": {
        "blood_type": "A-",
        "allergies": ["Peanuts"],
        "conditions": ["Epilepsy"],
        "medications": ["Levetiracetam 500mg", "Vitamin D3"],
        "emergency_contacts": [
            {"name": "Kavita Mehta", "phone": "+91 9000000004", "relation": "Mother"},
            {"name": "Ravi Mehta",   "phone": "+91 9000000005", "relation": "Brother"},
        ]
    },
}

def login(phone, pw):
    r = requests.post(f"{BASE}/auth/login",
        data={"username": phone, "password": pw},
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    return r.json()["access_token"]

def get_user_id(token):
    pt = token.split('.')[1]
    pt += '=' * (4 - len(pt) % 4)
    return json.loads(base64.b64decode(pt))["sub"]

def hdr(token):
    return {"Authorization": f"Bearer {token}"}

# ── Register ───────────────────────────────────────────────
print("\n── Registering users ──")
tokens = {}
for u in USERS:
    r = requests.post(f"{BASE}/auth/register", json=u)
    status = "✓ Registered" if r.status_code == 200 else "· Exists"
    print(f"  {status}: {u['name']} ({u['role']})")
    tokens[u["phone"]] = login(u["phone"], u["password"])

# ── Medical profiles ───────────────────────────────────────
print("\n── Seeding medical profiles ──")
for phone, profile in PROFILES.items():
    r = requests.put(f"{BASE}/medical/profile", json=profile, headers=hdr(tokens[phone]))
    print(f"  {'✓' if r.status_code==200 else '✗'} Profile: {phone}")

# ── SOS events — Ahmedabad locations ──────────────────────
print("\n── Seeding Ahmedabad SOS events ──")
patient_phones = ["9123456780", "9234567801", "9345678012"]
severities = ["severe", "severe", "moderate", "moderate", "moderate", "low"]
created = []

for i in range(14):
    phone = random.choice(patient_phones)
    token = tokens[phone]
    loc = random.choice(LOCATIONS)
    # small random offset so points don't stack
    lat = loc[0] + random.uniform(-0.008, 0.008)
    lon = loc[1] + random.uniform(-0.008, 0.008)
    sev = random.choice(severities)
    g   = round(random.uniform(7.0, 10.5) if sev == "severe" else random.uniform(2.5, 6.5), 2)

    r = requests.post(f"{BASE}/sos/trigger",
        json={"latitude": lat, "longitude": lon, "g_force_peak": g},
        headers=hdr(token))

    if r.status_code == 200:
        data = r.json()
        sos_id = data["sos_id"]
        auto_sev = data["severity"]
        created.append((sos_id, phone, token))
        print(f"  ✓ SOS #{i+1:02d}: {auto_sev:8} | G={g:.1f}g | {loc[2]}")
    else:
        print(f"  ✗ Failed: {r.text[:80]}")
    time.sleep(0.15)

# Cancel first 4
print("\n── Cancelling 4 events ──")
for sos_id, phone, token in created[:4]:
    r = requests.post(f"{BASE}/sos/{sos_id}/cancel", headers=hdr(token))
    print(f"  {'✓' if r.status_code==200 else '✗'} Cancelled {sos_id[:8]}…")

# ── Prescriptions ──────────────────────────────────────────
print("\n── Seeding prescriptions ──")
doctor_token = tokens["9876543210"]
rxs = [
    {"diagnosis": "Acute Hypertensive Crisis",
     "medicines": "Amlodipine 5mg OD, Losartan 50mg OD, Aspirin 75mg OD",
     "notes": "Monitor BP twice daily. Follow up in 2 weeks. Reduce salt intake."},
    {"diagnosis": "Acute Asthma Exacerbation",
     "medicines": "Salbutamol 2 puffs q4h, Prednisolone 40mg x5 days, Montelukast 10mg at night",
     "notes": "Use spacer. Avoid triggers. Return if no improvement in 48h."},
    {"diagnosis": "Post-Seizure Management",
     "medicines": "Levetiracetam 1000mg BD, Vitamin B6 50mg OD",
     "notes": "Do not drive. Avoid sleep deprivation. EEG scheduled next week."},
]
for i, phone in enumerate(patient_phones):
    pid = get_user_id(tokens[phone])
    r = requests.post(f"{BASE}/medical/prescription",
        json={"patient_id": pid, "content": rxs[i]},
        headers=hdr(doctor_token))
    print(f"  {'✓' if r.status_code==200 else '✗'} Rx for {phone}: {rxs[i]['diagnosis']}")

# ── Verify nearest hospital for Bopal ─────────────────────
print("\n── Nearest hospital check: Bopal (Vakil Saheb Bridge) ──")
r = requests.get(f"{BASE}/dispatch/nearest-hospital?lat=23.0225&lon=72.5714",
    headers=hdr(tokens["9999999999"]))
if r.status_code == 200:
    h = r.json()
    print(f"  🏥 {h['name']}")
    print(f"     Distance : {h['distance_km']} km")
    print(f"     Address  : {h.get('address') or 'N/A'}")
    print(f"     Phone    : {h.get('phone') or 'N/A'}")
    print(f"     Emergency: {h.get('emergency')}")
else:
    print(f"  ✗ {r.text}")

print("\n" + "="*52)
print("  ✓ Ahmedabad seed complete!")
print("="*52)
print("\nLogin credentials:")
for u in USERS:
    print(f"  {u['role']:8} | {u['phone']} / {u['password']}")
