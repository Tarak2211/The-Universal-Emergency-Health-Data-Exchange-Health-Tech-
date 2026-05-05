"""
SafePulse Dummy Data Seeder
Run: python seed.py
"""
import requests, json, random, time
from datetime import datetime, timedelta

BASE = "http://localhost:8000"

USERS = [
    {"name": "Tarak Admin",    "phone": "9999999999", "password": "Test@1234", "role": "admin"},
    {"name": "Dr. Priya Sharma","phone": "9876543210", "password": "Doctor@123", "role": "doctor"},
    {"name": "Rahul Verma",    "phone": "9123456780", "password": "Patient@123","role": "patient"},
    {"name": "Sneha Patel",    "phone": "9234567801", "password": "Patient@123","role": "patient"},
    {"name": "Arjun Mehta",    "phone": "9345678012", "password": "Patient@123","role": "patient"},
]

MEDICAL_PROFILES = {
    "9123456780": {
        "blood_type": "B+",
        "allergies": ["Penicillin", "Sulfa drugs"],
        "conditions": ["Type 2 Diabetes", "Hypertension"],
        "medications": ["Metformin 500mg", "Lisinopril 10mg", "Aspirin 75mg"],
        "emergency_contacts": [
            {"name": "Meena Verma", "phone": "+91 9000000001", "relation": "Spouse"},
            {"name": "Suresh Verma","phone": "+91 9000000002", "relation": "Father"}
        ]
    },
    "9234567801": {
        "blood_type": "O+",
        "allergies": ["Latex", "Ibuprofen"],
        "conditions": ["Asthma", "Anxiety Disorder"],
        "medications": ["Salbutamol Inhaler", "Montelukast 10mg"],
        "emergency_contacts": [
            {"name": "Raj Patel", "phone": "+91 9000000003", "relation": "Husband"}
        ]
    },
    "9345678012": {
        "blood_type": "A-",
        "allergies": ["Peanuts"],
        "conditions": ["Epilepsy"],
        "medications": ["Levetiracetam 500mg", "Vitamin D3"],
        "emergency_contacts": [
            {"name": "Kavita Mehta","phone": "+91 9000000004","relation": "Mother"},
            {"name": "Ravi Mehta",  "phone": "+91 9000000005","relation": "Brother"}
        ]
    }
}

# City coordinates (Mumbai area) for realistic hotspots
LOCATIONS = [
    (19.0760, 72.8777, "Bandra"),
    (19.1136, 72.8697, "Andheri"),
    (18.9220, 72.8347, "Colaba"),
    (19.0330, 72.8490, "Dadar"),
    (19.1663, 72.9479, "Powai"),
    (19.0596, 72.8295, "Worli"),
    (19.2183, 72.9781, "Thane"),
    (19.0728, 72.8826, "Kurla"),
]

def register_users():
    print("\n── Registering users ──")
    tokens = {}
    for u in USERS:
        r = requests.post(f"{BASE}/auth/register", json=u)
        if r.status_code == 200:
            print(f"  ✓ Registered: {u['name']} ({u['role']})")
        elif "already registered" in r.text:
            print(f"  · Exists:     {u['name']}")
        else:
            print(f"  ✗ Failed:     {u['name']} — {r.text}")

        # Login to get token
        lr = requests.post(f"{BASE}/auth/login",
            data={"username": u["phone"], "password": u["password"]},
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        if lr.status_code == 200:
            tokens[u["phone"]] = lr.json()["access_token"]
    return tokens

def seed_medical_profiles(tokens):
    print("\n── Seeding medical profiles ──")
    for phone, profile in MEDICAL_PROFILES.items():
        token = tokens.get(phone)
        if not token:
            print(f"  ✗ No token for {phone}")
            continue
        r = requests.put(f"{BASE}/medical/profile", json=profile,
            headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 200:
            print(f"  ✓ Profile set for {phone}")
        else:
            print(f"  ✗ Failed for {phone}: {r.text}")

def seed_sos_events(tokens):
    print("\n── Seeding SOS emergency events ──")
    patient_phones = ["9123456780", "9234567801", "9345678012"]
    severities = ["severe", "severe", "moderate", "moderate", "moderate", "low"]
    statuses   = ["triggered", "cancelled", "responded", "closed"]

    created = []
    for i in range(12):
        phone = random.choice(patient_phones)
        token = tokens.get(phone)
        if not token:
            continue

        loc = random.choice(LOCATIONS)
        # Add small random offset so points spread out
        lat = loc[0] + random.uniform(-0.02, 0.02)
        lon = loc[1] + random.uniform(-0.02, 0.02)
        sev = random.choice(severities)
        g   = round(random.uniform(3.5, 9.5) if sev == "severe" else random.uniform(2.0, 5.0), 2)

        r = requests.post(f"{BASE}/sos/trigger",
            json={"latitude": lat, "longitude": lon, "g_force_peak": g, "severity": sev},
            headers={"Authorization": f"Bearer {token}"})

        if r.status_code == 200:
            sos_id = r.json()["sos_id"]
            created.append((sos_id, phone, token, sev))
            print(f"  ✓ SOS #{i+1}: {sev} | G={g} | {loc[2]}")
        else:
            print(f"  ✗ SOS failed: {r.text}")

        time.sleep(0.1)

    # Cancel some, leave others triggered
    print("\n── Cancelling some SOS events ──")
    for sos_id, phone, token, sev in created[:4]:
        r = requests.post(f"{BASE}/sos/{sos_id}/cancel",
            headers={"Authorization": f"Bearer {token}"})
        if r.status_code == 200:
            print(f"  ✓ Cancelled: {sos_id[:8]}…")

    return created

def seed_prescriptions(tokens):
    print("\n── Seeding prescriptions ──")
    doctor_token = tokens.get("9876543210")
    if not doctor_token:
        print("  ✗ No doctor token")
        return

    # Get patient IDs first
    patient_phones = ["9123456780", "9234567801", "9345678012"]
    prescriptions = [
        {
            "diagnosis": "Acute Hypertensive Crisis",
            "medicines": "Amlodipine 5mg once daily, Losartan 50mg once daily, Aspirin 75mg once daily",
            "notes": "Monitor BP twice daily. Follow up in 2 weeks. Avoid salt intake."
        },
        {
            "diagnosis": "Acute Asthma Exacerbation",
            "medicines": "Salbutamol 2 puffs every 4 hours, Prednisolone 40mg for 5 days, Montelukast 10mg at night",
            "notes": "Use spacer with inhaler. Avoid triggers. Return if no improvement in 48 hours."
        },
        {
            "diagnosis": "Post-Seizure Management",
            "medicines": "Levetiracetam 1000mg twice daily, Vitamin B6 50mg once daily",
            "notes": "Do not drive. Avoid sleep deprivation. EEG scheduled next week."
        }
    ]

    for i, phone in enumerate(patient_phones):
        patient_token = tokens.get(phone)
        if not patient_token:
            continue

        # Get patient ID from their medical-id endpoint
        r = requests.get(f"{BASE}/sos/medical-id",
            headers={"Authorization": f"Bearer {patient_token}"})

        # We need the actual user ID — decode from JWT
        import base64
        pt = patient_token.split('.')[1]
        pt += '=' * (4 - len(pt) % 4)
        payload = json.loads(base64.b64decode(pt))
        patient_id = payload.get("sub")

        rx = prescriptions[i % len(prescriptions)]
        r = requests.post(f"{BASE}/medical/prescription",
            json={"patient_id": patient_id, "content": rx},
            headers={"Authorization": f"Bearer {doctor_token}"})

        if r.status_code == 200:
            print(f"  ✓ Prescription for patient {phone}: {rx['diagnosis']}")
        else:
            print(f"  ✗ Failed for {phone}: {r.text}")

def main():
    print("=" * 50)
    print("  SafePulse Data Seeder")
    print("=" * 50)

    # Check server
    try:
        r = requests.get(f"{BASE}/health", timeout=3)
        print(f"\n✓ Server online: {r.json()}")
    except Exception as e:
        print(f"\n✗ Server not reachable: {e}")
        print("  Make sure uvicorn is running on port 8000")
        return

    tokens = register_users()
    seed_medical_profiles(tokens)
    seed_sos_events(tokens)
    seed_prescriptions(tokens)

    print("\n" + "=" * 50)
    print("  ✓ Seeding complete!")
    print("=" * 50)
    print("\nLogin credentials:")
    for u in USERS:
        print(f"  {u['role']:8} | {u['phone']} / {u['password']}")

if __name__ == "__main__":
    main()
