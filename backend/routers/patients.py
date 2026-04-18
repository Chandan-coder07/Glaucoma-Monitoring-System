"""
Patients Router — extended with photo, discharge, age filter, emergency contact.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query, UploadFile, File
from pydantic import BaseModel
from routers.auth import get_current_user
import base64

router = APIRouter()

class DoctorAssign(BaseModel):
    doctor_id: str

class EmergencyContact(BaseModel):
    name: str
    phone: str
    relation: str

def require_doctor(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "doctor":
        raise HTTPException(status_code=403, detail="Doctor access required")
    return current_user

@router.get("/")
async def list_patients(
    request: Request,
    min_age: Optional[int] = Query(None),
    max_age: Optional[int] = Query(None),
    risk: Optional[str]    = Query(None),
    doctor_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_doctor),
):
    db = request.app.state.db
    query = {"role": "patient", "is_active": True}
    if min_age: query["age"] = {"$gte": min_age}
    if max_age:
        query.setdefault("age", {})
        query["age"]["$lte"] = max_age
    if doctor_id:
        query["assigned_doctor_id"] = doctor_id

    patients = []
    async for p in db.users.find(query):
        # Get latest measurement for risk filter
        latest = await db.measurements.find_one(
            {"patient_id": str(p["_id"])}, sort=[("timestamp", -1)]
        )
        latest_risk = latest["risk_level"] if latest else None
        if risk and latest_risk != risk:
            continue
        patients.append({
            "id":                 str(p["_id"]),
            "name":               p["name"],
            "email":              p["email"],
            "age":                p.get("age"),
            "cornea_thickness":   p.get("cornea_thickness"),
            "photo":              p.get("photo"),
            "assigned_doctor_id": p.get("assigned_doctor_id"),
            "emergency_contact":  p.get("emergency_contact"),
            "latest_iop":         latest["iop_value"]   if latest else None,
            "latest_risk":        latest_risk,
            "latest_timestamp":   latest["timestamp"].isoformat() if latest else None,
        })
    return {"patients": patients, "total": len(patients)}

@router.get("/{patient_id}")
async def get_patient(request: Request, patient_id: str,
                      current_user: dict = Depends(get_current_user)):
    db = request.app.state.db
    from bson import ObjectId

    if current_user["role"] == "patient" and current_user["sub"] != patient_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        patient = await db.users.find_one({"_id": ObjectId(patient_id)})
    except Exception:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    latest = await db.measurements.find_one(
        {"patient_id": patient_id}, sort=[("timestamp", -1)]
    )
    medicines = []
    async for m in db.medicines.find({"patient_id": patient_id}):
        medicines.append({
            "id":          str(m["_id"]),
            "name":        m["name"],
            "dosage":      m["dosage"],
            "frequency":   m["frequency"],
            "taken_today": m.get("taken_today", False),
        })

    return {
        "id":                 str(patient["_id"]),
        "name":               patient["name"],
        "email":              patient["email"],
        "age":                patient.get("age"),
        "cornea_thickness":   patient.get("cornea_thickness"),
        "photo":              patient.get("photo"),
        "assigned_doctor_id": patient.get("assigned_doctor_id"),
        "emergency_contact":  patient.get("emergency_contact"),
        "latest_iop":         latest["iop_value"]              if latest else None,
        "latest_risk":        latest["risk_level"]             if latest else None,
        "latest_timestamp":   latest["timestamp"].isoformat()  if latest else None,
        "medicines":          medicines,
    }

@router.put("/{patient_id}/assign-doctor")
async def assign_doctor(request: Request, patient_id: str, body: DoctorAssign,
                        current_user: dict = Depends(require_doctor)):
    from bson import ObjectId
    db = request.app.state.db
    await db.users.update_one(
        {"_id": ObjectId(patient_id)},
        {"$set": {"assigned_doctor_id": body.doctor_id}}
    )
    return {"success": True}

@router.put("/{patient_id}/discharge")
async def discharge_patient(request: Request, patient_id: str,
                             current_user: dict = Depends(require_doctor)):
    from bson import ObjectId
    db = request.app.state.db
    await db.users.update_one(
        {"_id": ObjectId(patient_id)},
        {"$set": {"is_active": False, "discharged_at": datetime.utcnow()}}
    )
    return {"success": True}

@router.put("/{patient_id}/emergency-contact")
async def set_emergency_contact(request: Request, patient_id: str,
                                body: EmergencyContact,
                                current_user: dict = Depends(get_current_user)):
    from bson import ObjectId
    db = request.app.state.db
    await db.users.update_one(
        {"_id": ObjectId(patient_id)},
        {"$set": {"emergency_contact": body.dict()}}
    )
    return {"success": True}

@router.post("/{patient_id}/photo")
async def upload_photo(request: Request, patient_id: str,
                       file: UploadFile = File(...),
                       current_user: dict = Depends(get_current_user)):
    from bson import ObjectId
    db      = request.app.state.db
    content = await file.read()
    # Store as base64 (for small profile photos only)
    b64     = "data:" + file.content_type + ";base64," + base64.b64encode(content).decode()
    await db.users.update_one(
        {"_id": ObjectId(patient_id)},
        {"$set": {"photo": b64}}
    )
    return {"success": True, "photo": b64}

@router.put("/medicines/{medicine_id}/taken")
async def mark_medicine_taken(request: Request, medicine_id: str,
                               current_user: dict = Depends(get_current_user)):
    from bson import ObjectId
    db = request.app.state.db
    await db.medicines.update_one(
        {"_id": ObjectId(medicine_id)},
        {"$set": {"taken_today": True, "last_taken": datetime.utcnow()}}
    )
    return {"success": True}

@router.post("/medicines")
async def add_medicine(request: Request, current_user: dict = Depends(get_current_user)):
    from pydantic import BaseModel as BM
    db = request.app.state.db
    body = await request.json()
    doc = {
        "patient_id": body["patient_id"],
        "name":       body["name"],
        "dosage":     body["dosage"],
        "frequency":  body["frequency"],
        "start_date": datetime.utcnow(),
        "taken_today": False,
    }
    result = await db.medicines.insert_one(doc)
    return {"id": str(result.inserted_id), "success": True}

@router.delete("/medicines/{medicine_id}")
async def delete_medicine(request: Request, medicine_id: str,
                          current_user: dict = Depends(require_doctor)):
    from bson import ObjectId
    db = request.app.state.db
    await db.medicines.delete_one({"_id": ObjectId(medicine_id)})
    return {"success": True}
