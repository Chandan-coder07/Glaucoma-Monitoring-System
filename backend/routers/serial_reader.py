"""
Serial Reader v3 — Real HX710B pressure sensor via ESP32 USB Serial.
Handles: IOP data, pump control, calibration commands.
"""
import asyncio
import re
import os
import random
from datetime import datetime

READ_INTERVAL = int(os.getenv("READ_INTERVAL_SECONDS", "5"))


class SerialReader:
    def __init__(self, port: str, baud_rate: int, ws_manager, alert_service):
        self.port          = port
        self.baud_rate     = baud_rate
        self.ws_manager    = ws_manager
        self.alert_service = alert_service
        self.is_connected  = False
        self._running      = False
        self._demo_mode    = False
        self._db           = None
        self._writer       = None   # keep reference to send commands to ESP32

    async def start(self, db):
        self._running = True
        self._db      = db
        try:
            await self._serial_loop()
        except Exception as e:
            print(f"⚠️  Serial unavailable: {e}")
            print(f"   Port tried: {self.port}")
            print(f"   Run: ls /dev/tty.* to find your ESP32 port")
            print(f"📡 Falling back to DEMO MODE")
            self._demo_mode = True
            await self._demo_loop()

    # ── Send command to ESP32 ─────────────────────────────────────────────────
    async def send_command(self, cmd: str):
        if self._writer and self.is_connected:
            self._writer.write((cmd + "\n").encode())
            await self._writer.drain()
            print(f"→ ESP32: {cmd}")

    # ── Real Serial Loop ──────────────────────────────────────────────────────
    async def _serial_loop(self):
        import serial_asyncio

        print(f"🔌 Connecting to ESP32 on {self.port} @ {self.baud_rate} baud...")
        reader, writer = await serial_asyncio.open_serial_connection(
            url=self.port, baudrate=self.baud_rate
        )
        self._writer      = writer
        self.is_connected = True
        print(f"✅ ESP32 CONNECTED on {self.port}")

        # Ping to verify
        await self.send_command("PING")

        while self._running:
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=30.0)
                raw  = line.decode("utf-8", errors="ignore").strip()

                if not raw:
                    continue

                # Log ESP32 status messages
                if any(raw.startswith(p) for p in [
                    "GlaucoMonitor", "Format:", "Sending", "---",
                    "PONG", "STATUS:", "OFFSET:", "CALIBRAT",
                    "PUMP:", "MEASURE:", "SCALE_SET:", "PATIENT_SET:",
                    "ERR:", "Ready"
                ]):
                    print(f"   ESP32 → {raw}")
                    continue

                # Process actual IOP reading
                if "IOP:" in raw:
                    await self._process_iop_line(raw)
                elif raw.startswith("RAW:"):
                    print(f"   RAW DATA → {raw}")

            except asyncio.TimeoutError:
                print("⏳ No data from ESP32 for 30s, pinging...")
                await self.send_command("PING")
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Serial error: {e}")
                await asyncio.sleep(2)

        self.is_connected = False
        self._writer      = None

    # ── Parse IOP Line ────────────────────────────────────────────────────────
    async def _process_iop_line(self, raw: str):
        """
        Parse: IOP:18.5,EYE:RIGHT,PATIENT:default,RAW:123456
        """
        try:
            iop_val    = None
            eye        = "RIGHT"
            patient_id = None

            m_iop = re.search(r"IOP:([\d.]+)",   raw)
            m_eye = re.search(r"EYE:(\w+)",       raw)
            m_pat = re.search(r"PATIENT:(\w+)",   raw)
            m_raw = re.search(r"RAW:(-?[\d]+)",   raw)

            if m_iop: iop_val    = float(m_iop.group(1))
            if m_eye: eye        = m_eye.group(1).upper()
            if m_pat: patient_id = m_pat.group(1)

            if iop_val is None:
                print(f"   ⚠️  Could not parse IOP from: {raw}")
                return

            # Validate range
            if not (5.0 <= iop_val <= 40.0):
                print(f"   ⚠️  IOP {iop_val} out of range — check sensor calibration")
                return

            # Resolve patient
            if not patient_id or patient_id == "default":
                pt = await self._db.users.find_one({"role": "patient", "is_active": True})
                if not pt:
                    print("   ⚠️  No active patient found in database")
                    return
                patient_id = str(pt["_id"])
                age        = pt.get("age", 60)
                cornea     = pt.get("cornea_thickness", 540.0)
            else:
                from bson import ObjectId
                try:
                    pt = await self._db.users.find_one({"_id": ObjectId(patient_id)})
                except Exception:
                    pt = await self._db.users.find_one({"role": "patient", "is_active": True})
                age    = pt.get("age", 60)                if pt else 60
                cornea = pt.get("cornea_thickness", 540.0) if pt else 540.0

            await self._save_and_broadcast(patient_id, iop_val, eye, age, cornea)

        except Exception as e:
            print(f"   ❌ Parse error '{raw}': {e}")

    # ── Demo Mode ─────────────────────────────────────────────────────────────
    async def _demo_loop(self):
        self.is_connected = True
        while self._running:
            try:
                patients = await self._db.users.find(
                    {"role": "patient", "is_active": True}
                ).to_list(100)
                for p in patients:
                    pid    = str(p["_id"])
                    age    = p.get("age", 60)
                    cornea = p.get("cornea_thickness", 540.0)
                    base   = p.get("base_iop", 18.5)
                    iop    = round(max(8.0, min(35.0, base + random.gauss(0, 2.5))), 1)
                    eye    = random.choice(["RIGHT", "LEFT"])
                    await self._save_and_broadcast(pid, iop, eye, age, cornea)
                await asyncio.sleep(READ_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Demo error: {e}")
                await asyncio.sleep(READ_INTERVAL)

    # ── Save + Broadcast ──────────────────────────────────────────────────────
    async def _save_and_broadcast(self, patient_id, iop, eye, age, cornea):
        from services.ml_service import predict_risk
        from bson import ObjectId

        threshold        = float(os.getenv("IOP_ALERT_THRESHOLD", "21"))
        risk_level, risk_prob = predict_risk(iop, age, cornea)
        now = datetime.utcnow()

        doc = {
            "patient_id":       patient_id,
            "iop_value":        iop,
            "risk_level":       risk_level,
            "risk_probability": round(risk_prob, 4),
            "eye":              eye,
            "timestamp":        now,
            "alert_sent":       False,
        }
        result = await self._db.measurements.insert_one(doc)
        mid    = str(result.inserted_id)

        if iop > threshold:
            try:
                pt = await self._db.users.find_one({"_id": ObjectId(patient_id)})
                if pt:
                    await self.alert_service.send_high_iop_alert(
                        patient_name=pt.get("name", "Patient"),
                        patient_email=pt.get("email"),
                        iop_value=iop,
                        risk_level=risk_level,
                        patient_id=patient_id,
                        emergency_contact=pt.get("emergency_contact"),
                    )
                    await self._db.measurements.update_one(
                        {"_id": result.inserted_id},
                        {"$set": {"alert_sent": True}}
                    )
            except Exception as e:
                print(f"Alert error: {e}")

        await self.ws_manager.broadcast_measurement(patient_id, {
            "id": mid, "patient_id": patient_id,
            "iop_value": iop, "risk_level": risk_level,
            "risk_probability": risk_prob,
            "eye": eye, "timestamp": now.isoformat(),
        })

        src = "📡 REAL" if not self._demo_mode else "🎲 DEMO"
        print(f"{src} | IOP:{iop:5.1f} mmHg | {risk_level:<6} | {eye:<5} | …{patient_id[-6:]}")