"""
Database models + seeding — Pydantic v2, Python 3.11+
Includes 5 demo patients with varied profiles.
"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, EmailStr, ConfigDict, BeforeValidator
from typing_extensions import Annotated
from bson import ObjectId


def _validate_oid(v: Any) -> ObjectId:
    if isinstance(v, ObjectId): return v
    if ObjectId.is_valid(v):    return ObjectId(str(v))
    raise ValueError(f"Invalid ObjectId: {v!r}")

PyObjectId = Annotated[ObjectId, BeforeValidator(_validate_oid)]

_cfg = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True,
                  json_encoders={ObjectId: str})


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "patient"
    age: Optional[int] = None
    cornea_thickness: Optional[float] = 540.0

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    name: str

class MeasurementCreate(BaseModel):
    patient_id: str
    iop_value: float
    eye: str = "RIGHT"
    notes: Optional[str] = None


async def init_db(db) -> None:
    await db.users.create_index("email", unique=True)
    await db.measurements.create_index([("patient_id", 1), ("timestamp", -1)])
    await db.medicines.create_index("patient_id")
    await db.messages.create_index([("from_user_id", 1), ("to_user_id", 1)])
    await db.doctor_notes.create_index([("patient_id", 1)])
    await db.appointments.create_index([("patient_id", 1), ("scheduled_at", 1)])
    await db.symptoms.create_index([("patient_id", 1), ("timestamp", -1)])
    await db.lifestyle.create_index([("patient_id", 1), ("timestamp", -1)])
    print("✅ Database indexes created")

    if await db.users.count_documents({}) == 0:
        await _seed(db)


async def _seed(db) -> None:
    from services.auth_service import hash_password
    from services.ml_service import predict_risk
    import random
    from datetime import timedelta

    now = datetime.utcnow()

    # ── Doctor ────────────────────────────────────────────────────────────────
    doctor = {
        "name": "Dr. Sarah Mitchell", "email": "doctor@glaucoma.demo",
        "hashed_password": hash_password("doctor123"),
        "role": "doctor", "age": 45, "created_at": now, "is_active": True,
        "hospital": "City Eye Clinic",
    }
    dr_res = await db.users.insert_one(doctor)
    dr_id  = str(dr_res.inserted_id)

    # ── 5 Demo Patients ────────────────────────────────────────────────────────
    demo_patients = [
        {"name":"John Anderson",    "email":"patient@glaucoma.demo",   "password":"patient123", "age":62, "cornea":520.0, "base_iop":20.5},
        {"name":"Priya Sharma",     "email":"priya@glaucoma.demo",     "password":"demo123",    "age":55, "cornea":545.0, "base_iop":17.2},
        {"name":"Ravi Kumar",       "email":"ravi@glaucoma.demo",      "password":"demo123",    "age":70, "cornea":495.0, "base_iop":23.1},
        {"name":"Meena Patel",      "email":"meena@glaucoma.demo",     "password":"demo123",    "age":48, "cornea":560.0, "base_iop":15.8},
        {"name":"Suresh Nair",      "email":"suresh@glaucoma.demo",    "password":"demo123",    "age":65, "cornea":510.0, "base_iop":21.8},
    ]

    for p in demo_patients:
        p_doc = {
            "name": p["name"], "email": p["email"],
            "hashed_password": hash_password(p["password"]),
            "role": "patient", "age": p["age"],
            "cornea_thickness": p["cornea"],
            "assigned_doctor_id": dr_id,
            "created_at": now, "is_active": True,
            "emergency_contact": {"name": "Family Member", "phone": "+91-9000000000", "relation": "Spouse"},
        }
        p_res = await db.users.insert_one(p_doc)
        pid   = str(p_res.inserted_id)

        # 30 measurements per patient
        measurements = []
        for i in range(30):
            iop   = round(max(8.0, min(35.0, p["base_iop"] + random.gauss(0, 2.5))), 1)
            rl, rp = predict_risk(iop, p["age"], p["cornea"])
            measurements.append({
                "patient_id": pid, "iop_value": iop,
                "risk_level": rl, "risk_probability": rp,
                "eye": "RIGHT" if i % 2 == 0 else "LEFT",
                "timestamp": now - timedelta(hours=i * 4), "alert_sent": False,
            })
        await db.measurements.insert_many(measurements)

        # Medicines
        await db.medicines.insert_many([
            {"patient_id":pid,"name":"Timolol","dosage":"0.5%","frequency":"twice_daily",
             "start_date":now-timedelta(days=30),"taken_today":True,"last_taken":now-timedelta(hours=6)},
            {"patient_id":pid,"name":"Latanoprost","dosage":"0.005%","frequency":"evening",
             "start_date":now-timedelta(days=30),"taken_today":False,"last_taken":now-timedelta(hours=20)},
        ])

        # Doctor note
        await db.doctor_notes.insert_one({
            "doctor_id": dr_id, "patient_id": pid,
            "content": f"Initial assessment. IOP baseline {p['base_iop']} mmHg. Continue current medication.",
            "visit_date": now - timedelta(days=7), "created_at": now - timedelta(days=7),
        })

        # Appointment
        await db.appointments.insert_one({
            "patient_id": pid, "doctor_id": dr_id,
            "scheduled_at": now + timedelta(days=random.randint(3, 14)),
            "notes": "Follow-up IOP check", "status": "scheduled",
            "meet_link": "https://meet.google.com/demo-link",
            "created_at": now,
        })

    print("✅ Demo data seeded — 1 doctor + 5 patients")
    print("   doctor@glaucoma.demo / doctor123")
    print("   patient@glaucoma.demo / patient123")
    print("   priya@glaucoma.demo, ravi@glaucoma.demo, meena@glaucoma.demo, suresh@glaucoma.demo / demo123")
