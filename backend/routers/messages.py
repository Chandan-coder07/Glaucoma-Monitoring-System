"""
Messages Router — in-app messaging between doctor and patient.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from routers.auth import get_current_user

router = APIRouter()

class MessageCreate(BaseModel):
    to_user_id: str
    content: str

class NoteCreate(BaseModel):
    patient_id: str
    content: str
    visit_date: Optional[datetime] = None

class AppointmentCreate(BaseModel):
    patient_id: str
    doctor_id: str
    scheduled_at: datetime
    notes: Optional[str] = None
    meet_link: Optional[str] = None

class SymptomCreate(BaseModel):
    eye_pain: bool = False
    blurriness: bool = False
    headache: bool = False
    redness: bool = False
    severity: int = 1  # 1-5
    notes: Optional[str] = None

class LifestyleCreate(BaseModel):
    sleep_hours: Optional[float] = None
    exercise_minutes: Optional[int] = None
    stress_level: Optional[int] = None  # 1-5
    water_intake_ml: Optional[int] = None

@router.post("/send")
async def send_message(request: Request, body: MessageCreate,
                       current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    doc = {
        "from_user_id": current_user["sub"],
        "to_user_id":   body.to_user_id,
        "content":      body.content,
        "timestamp":    datetime.utcnow(),
        "read":         False,
    }
    result = await db.messages.insert_one(doc)
    return {"id": str(result.inserted_id), "success": True}

@router.get("/thread/{other_user_id}")
async def get_thread(request: Request, other_user_id: str,
                     current_user: dict = Depends(get_current_user)):
    db  = request.app.state.db
    uid = current_user["sub"]
    cursor = db.messages.find({
        "$or": [
            {"from_user_id": uid, "to_user_id": other_user_id},
            {"from_user_id": other_user_id, "to_user_id": uid},
        ]
    }, sort=[("timestamp", 1)]).limit(100)
    msgs = []
    async for m in cursor:
        msgs.append({
            "id":           str(m["_id"]),
            "from_user_id": m["from_user_id"],
            "to_user_id":   m["to_user_id"],
            "content":      m["content"],
            "timestamp":    m["timestamp"].isoformat(),
            "read":         m.get("read", False),
            "mine":         m["from_user_id"] == uid,
        })
    # Mark as read
    await db.messages.update_many(
        {"from_user_id": other_user_id, "to_user_id": uid, "read": False},
        {"$set": {"read": True}}
    )
    return {"messages": msgs}

@router.get("/unread-count")
async def unread_count(request: Request, current_user: dict = Depends(get_current_user)):
    db    = request.app.state.db
    count = await db.messages.count_documents({"to_user_id": current_user["sub"], "read": False})
    return {"count": count}

@router.get("/inbox")
async def get_inbox(request: Request, current_user: dict = Depends(get_current_user)):
    db  = request.app.state.db
    uid = current_user["sub"]
    # Get latest message per conversation partner
    pipeline = [
        {"$match": {"$or": [{"from_user_id": uid}, {"to_user_id": uid}]}},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": {"$cond": [{"$eq": ["$from_user_id", uid]}, "$to_user_id", "$from_user_id"]},
            "last_message": {"$first": "$content"},
            "timestamp":    {"$first": "$timestamp"},
            "unread":       {"$sum": {"$cond": [{"$and": [{"$eq": ["$to_user_id", uid]}, {"$eq": ["$read", False]}]}, 1, 0]}},
        }},
    ]
    convos = []
    async for c in db.messages.aggregate(pipeline):
        from bson import ObjectId
        partner = await db.users.find_one({"_id": ObjectId(c["_id"])})
        if partner:
            convos.append({
                "partner_id":   c["_id"],
                "partner_name": partner.get("name", "Unknown"),
                "partner_role": partner.get("role", ""),
                "last_message": c["last_message"],
                "timestamp":    c["timestamp"].isoformat(),
                "unread":       c["unread"],
            })
    return {"conversations": convos}

# ── Doctor Notes ──────────────────────────────────────────────────────────────
@router.post("/notes")
async def add_note(request: Request, body: NoteCreate,
                   current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "doctor":
        raise HTTPException(403, "Doctor only")
    db  = request.app.state.db
    doc = {
        "doctor_id":  current_user["sub"],
        "patient_id": body.patient_id,
        "content":    body.content,
        "visit_date": body.visit_date or datetime.utcnow(),
        "created_at": datetime.utcnow(),
    }
    result = await db.doctor_notes.insert_one(doc)
    return {"id": str(result.inserted_id), "success": True}

@router.get("/notes/{patient_id}")
async def get_notes(request: Request, patient_id: str,
                    current_user: dict = Depends(get_current_user)):
    db    = request.app.state.db
    notes = []
    async for n in db.doctor_notes.find({"patient_id": patient_id}, sort=[("created_at", -1)]):
        notes.append({
            "id":         str(n["_id"]),
            "content":    n["content"],
            "visit_date": n["visit_date"].isoformat(),
            "created_at": n["created_at"].isoformat(),
        })
    return {"notes": notes}

# ── Appointments ──────────────────────────────────────────────────────────────
@router.post("/appointments")
async def create_appointment(request: Request, body: AppointmentCreate,
                             current_user: dict = Depends(get_current_user)):
    db  = request.app.state.db
    doc = {
        "patient_id":    body.patient_id,
        "doctor_id":     body.doctor_id,
        "scheduled_at":  body.scheduled_at,
        "notes":         body.notes,
        "meet_link":     body.meet_link,
        "status":        "scheduled",
        "created_at":    datetime.utcnow(),
    }
    result = await db.appointments.insert_one(doc)
    return {"id": str(result.inserted_id), "success": True}

@router.get("/appointments/{user_id}")
async def get_appointments(request: Request, user_id: str,
                           current_user: dict = Depends(get_current_user)):
    db   = request.app.state.db
    role = current_user["role"]
    q    = {"doctor_id": user_id} if role == "doctor" else {"patient_id": user_id}
    appts = []
    async for a in db.appointments.find(q, sort=[("scheduled_at", 1)]):
        from bson import ObjectId
        other_id   = a["patient_id"] if role == "doctor" else a["doctor_id"]
        other_user = await db.users.find_one({"_id": ObjectId(other_id)})
        appts.append({
            "id":           str(a["_id"]),
            "other_name":   other_user.get("name", "Unknown") if other_user else "Unknown",
            "scheduled_at": a["scheduled_at"].isoformat(),
            "notes":        a.get("notes", ""),
            "meet_link":    a.get("meet_link", ""),
            "status":       a.get("status", "scheduled"),
        })
    return {"appointments": appts}

@router.put("/appointments/{appt_id}/status")
async def update_appointment_status(request: Request, appt_id: str,
                                    status: str, current_user: dict = Depends(get_current_user)):
    from bson import ObjectId
    db = request.app.state.db
    await db.appointments.update_one(
        {"_id": ObjectId(appt_id)},
        {"$set": {"status": status}}
    )
    return {"success": True}

# ── Symptoms ──────────────────────────────────────────────────────────────────
@router.post("/symptoms")
async def log_symptom(request: Request, body: SymptomCreate,
                      current_user: dict = Depends(get_current_user)):
    db  = request.app.state.db
    doc = {
        "patient_id":  current_user["sub"],
        "eye_pain":    body.eye_pain,
        "blurriness":  body.blurriness,
        "headache":    body.headache,
        "redness":     body.redness,
        "severity":    body.severity,
        "notes":       body.notes,
        "timestamp":   datetime.utcnow(),
    }
    result = await db.symptoms.insert_one(doc)
    return {"id": str(result.inserted_id), "success": True}

@router.get("/symptoms/{patient_id}")
async def get_symptoms(request: Request, patient_id: str,
                       current_user: dict = Depends(get_current_user)):
    db      = request.app.state.db
    symptoms = []
    async for s in db.symptoms.find({"patient_id": patient_id}, sort=[("timestamp", -1)]).limit(30):
        symptoms.append({
            "id":         str(s["_id"]),
            "eye_pain":   s.get("eye_pain", False),
            "blurriness": s.get("blurriness", False),
            "headache":   s.get("headache", False),
            "redness":    s.get("redness", False),
            "severity":   s.get("severity", 1),
            "notes":      s.get("notes", ""),
            "timestamp":  s["timestamp"].isoformat(),
        })
    return {"symptoms": symptoms}

# ── Lifestyle ─────────────────────────────────────────────────────────────────
@router.post("/lifestyle")
async def log_lifestyle(request: Request, body: LifestyleCreate,
                        current_user: dict = Depends(get_current_user)):
    db  = request.app.state.db
    doc = {
        "patient_id":       current_user["sub"],
        "sleep_hours":      body.sleep_hours,
        "exercise_minutes": body.exercise_minutes,
        "stress_level":     body.stress_level,
        "water_intake_ml":  body.water_intake_ml,
        "timestamp":        datetime.utcnow(),
    }
    result = await db.lifestyle.insert_one(doc)
    return {"id": str(result.inserted_id), "success": True}

@router.get("/lifestyle/{patient_id}")
async def get_lifestyle(request: Request, patient_id: str,
                        current_user: dict = Depends(get_current_user)):
    db      = request.app.state.db
    entries = []
    async for e in db.lifestyle.find({"patient_id": patient_id}, sort=[("timestamp", -1)]).limit(30):
        entries.append({
            "id":               str(e["_id"]),
            "sleep_hours":      e.get("sleep_hours"),
            "exercise_minutes": e.get("exercise_minutes"),
            "stress_level":     e.get("stress_level"),
            "water_intake_ml":  e.get("water_intake_ml"),
            "timestamp":        e["timestamp"].isoformat(),
        })
    return {"entries": entries}
