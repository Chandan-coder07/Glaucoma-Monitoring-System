"""
GlaucoMonitor — FastAPI backend (v2 with all enhancements).
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

from routers import auth, patients, measurements, reports, messages
from services.websocket_manager import WebSocketManager
from services.alert_service import AlertService
from services.serial_reader import SerialReader
from models.database import init_db

MONGO_URL    = os.getenv("MONGO_URL",    "mongodb://localhost:27017")
DB_NAME      = os.getenv("DB_NAME",      "glaucoma_monitor")
SERIAL_PORT  = os.getenv("SERIAL_PORT",  "/dev/tty.usbserial-0001")
BAUD_RATE    = int(os.getenv("BAUD_RATE", "9600"))
HOSPITAL_NAME = os.getenv("HOSPITAL_NAME", "GlaucoMonitor Clinic")
IOP_THRESHOLD = float(os.getenv("IOP_ALERT_THRESHOLD", "21"))
READ_INTERVAL = int(os.getenv("READ_INTERVAL_SECONDS", "5"))

ws_manager    = WebSocketManager()
alert_service = AlertService()
serial_reader = SerialReader(
    port=SERIAL_PORT, baud_rate=BAUD_RATE,
    ws_manager=ws_manager, alert_service=alert_service,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    try:
        await client.admin.command("ping")
        print(f"✅ MongoDB connected: {MONGO_URL}")
    except Exception as e:
        print(f"❌ MongoDB failed: {e}")
        raise
    app.state.db            = client[DB_NAME]
    app.state.hospital_name = HOSPITAL_NAME
    app.state.iop_threshold = IOP_THRESHOLD
    await init_db(app.state.db)

    serial_task = asyncio.create_task(serial_reader.start(app.state.db))
    yield

    serial_task.cancel()
    try:
        await serial_task
    except asyncio.CancelledError:
        pass
    client.close()
    print("🛑 Shutdown complete")


app = FastAPI(title="GlaucoMonitor API", version="2.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth.router,         prefix="/api/auth",         tags=["Auth"])
app.include_router(patients.router,     prefix="/api/patients",     tags=["Patients"])
app.include_router(measurements.router, prefix="/api/measurements", tags=["Measurements"])
app.include_router(reports.router,      prefix="/api/reports",      tags=["Reports"])
app.include_router(messages.router,     prefix="/api/messages",     tags=["Messages"])


@app.websocket("/ws/{patient_id}")
async def ws_endpoint(websocket: WebSocket, patient_id: str):
    await ws_manager.connect(websocket, patient_id)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, patient_id)


@app.get("/health")
async def health():
    return {
        "status":        "healthy",
        "timestamp":     datetime.utcnow().isoformat(),
        "serial":        serial_reader.is_connected,
        "demo_mode":     serial_reader._demo_mode,
        "hospital":      HOSPITAL_NAME,
        "iop_threshold": IOP_THRESHOLD,
    }

@app.get("/api/config")
async def get_config():
    """Frontend reads this to get hospital name, threshold etc."""
    return {
        "hospital_name":   HOSPITAL_NAME,
        "iop_threshold":   IOP_THRESHOLD,
        "read_interval":   READ_INTERVAL,
    }
