"""
Measurements Router
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query

from models.database import MeasurementCreate
from routers.auth import get_current_user
from services.ml_service import predict_risk, get_risk_summary

router = APIRouter()


@router.get("/history")
async def get_history(
    request: Request,
    patient_id: Optional[str] = Query(None),
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    db        = request.app.state.db
    user_role = current_user["role"]
    user_id   = current_user["sub"]

    if user_role == "patient":
        target_id = user_id
    elif user_role == "doctor":
        target_id = patient_id if patient_id else user_id
    else:
        raise HTTPException(status_code=403, detail="Unauthorized")

    cutoff = datetime.utcnow() - timedelta(days=days)
    cursor = db.measurements.find(
        {"patient_id": target_id, "timestamp": {"$gte": cutoff}},
        sort=[("timestamp", -1)],
    ).limit(limit)

    measurements = []
    async for m in cursor:
        measurements.append({
            "id":               str(m["_id"]),
            "patient_id":       m["patient_id"],
            "iop_value":        m["iop_value"],
            "risk_level":       m["risk_level"],
            "risk_probability": m.get("risk_probability", 0),
            "eye":              m.get("eye", "RIGHT"),
            "timestamp":        m["timestamp"].isoformat(),
            "notes":            m.get("notes"),
        })

    return {
        "measurements": measurements,
        "total":        len(measurements),
        "summary":      get_risk_summary(measurements),
    }


@router.post("/")
async def create_measurement(
    request: Request,
    body: MeasurementCreate,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db
    from bson import ObjectId

    try:
        patient = await db.users.find_one({"_id": ObjectId(body.patient_id)})
    except Exception:
        patient = None

    age    = patient.get("age", 60)                   if patient else 60
    cornea = patient.get("cornea_thickness", 540.0)   if patient else 540.0

    risk_level, risk_prob = predict_risk(body.iop_value, age, cornea)

    doc = {
        "patient_id":       body.patient_id,
        "iop_value":        body.iop_value,
        "risk_level":       risk_level,
        "risk_probability": round(risk_prob, 4),
        "eye":              body.eye,
        "timestamp":        datetime.utcnow(),
        "notes":            body.notes,
        "alert_sent":       False,
    }
    result  = await db.measurements.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc["timestamp"] = doc["timestamp"].isoformat()
    return doc


@router.get("/latest/{patient_id}")
async def get_latest(
    request: Request,
    patient_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = request.app.state.db

    if current_user["role"] == "patient" and current_user["sub"] != patient_id:
        raise HTTPException(status_code=403, detail="Access denied")

    m = await db.measurements.find_one(
        {"patient_id": patient_id}, sort=[("timestamp", -1)]
    )
    if not m:
        return {"message": "No measurements found"}

    return {
        "id":               str(m["_id"]),
        "iop_value":        m["iop_value"],
        "risk_level":       m["risk_level"],
        "risk_probability": m.get("risk_probability", 0),
        "eye":              m.get("eye", "RIGHT"),
        "timestamp":        m["timestamp"].isoformat(),
    }
