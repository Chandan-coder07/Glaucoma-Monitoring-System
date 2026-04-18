"""
Serial Reader Service - Reads IOP data from ESP32 via USB Serial.
Continuously reads serial port, parses IOP values, stores in DB,
runs AI prediction, and broadcasts via WebSocket.

Expected serial format from ESP32:
    IOP:18.5,EYE:RIGHT,PATIENT:patient_id_here\n
    OR simple format:
    18.5\n  (for testing)
"""

import asyncio
import json
import re
import random
from datetime import datetime
from typing import Optional


class SerialReader:
    """Async serial port reader for ESP32 IOP sensor data."""

    def __init__(self, port: str, baud_rate: int, ws_manager, alert_service):
        self.port = port
        self.baud_rate = baud_rate
        self.ws_manager = ws_manager
        self.alert_service = alert_service
        self.is_connected = False
        self._running = False
        self._demo_mode = False  # Falls back to demo if no serial port

    async def start(self, db):
        """Start the serial reading loop."""
        self._running = True
        self._db = db
        try:
            await self._read_serial()
        except Exception as e:
            print(f"⚠️  Serial port unavailable ({e}), switching to DEMO mode")
            self._demo_mode = True
            await self._demo_mode_loop()

    async def _read_serial(self):
        """Read from actual serial port using serial_asyncio."""
        import serial_asyncio

        reader, writer = await serial_asyncio.open_serial_connection(
            url=self.port,
            baudrate=self.baud_rate,
        )
        self.is_connected = True
        print(f"✅ Serial connected: {self.port} @ {self.baud_rate} baud")

        while self._running:
            try:
                line = await reader.readline()
                raw = line.decode("utf-8", errors="ignore").strip()
                if raw:
                    await self._process_raw_line(raw)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Serial read error: {e}")
                await asyncio.sleep(1)

        self.is_connected = False

    async def _demo_mode_loop(self):
        """
        Simulate ESP32 data for development/demo purposes.
        Sends realistic IOP readings every 5 seconds.
        """
        self.is_connected = True
        print("📡 Demo mode: Simulating ESP32 data every 5 seconds")

        # Get all patient IDs from DB
        while self._running:
            try:
                patients = await self._db.users.find({"role": "patient"}).to_list(100)
                for patient in patients:
                    patient_id = str(patient["_id"])
                    age = patient.get("age", 60)
                    cornea = patient.get("cornea_thickness", 540.0)

                    # Simulate realistic IOP (slightly elevated to show alerts)
                    base_iop = 18.5
                    noise = random.gauss(0, 2.5)
                    iop_value = round(max(8.0, min(35.0, base_iop + noise)), 1)
                    eye = random.choice(["RIGHT", "LEFT"])

                    await self._save_and_broadcast(
                        patient_id=patient_id,
                        iop_value=iop_value,
                        eye=eye,
                        age=age,
                        cornea_thickness=cornea,
                    )
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Demo mode error: {e}")
                await asyncio.sleep(5)

    async def _process_raw_line(self, raw: str):
        """
        Parse a raw serial line from ESP32.
        Supports formats:
          - "IOP:18.5,EYE:RIGHT,PATIENT:abc123"
          - "18.5"  (bare IOP value, uses first patient)
        """
        try:
            iop_value = None
            eye = "RIGHT"
            patient_id = None

            # Full format
            if "IOP:" in raw:
                iop_match = re.search(r"IOP:([\d.]+)", raw)
                eye_match = re.search(r"EYE:(\w+)", raw)
                patient_match = re.search(r"PATIENT:(\w+)", raw)

                if iop_match:
                    iop_value = float(iop_match.group(1))
                if eye_match:
                    eye = eye_match.group(1).upper()
                if patient_match:
                    patient_id = patient_match.group(1)
            else:
                # Try bare float
                iop_value = float(raw)

            if iop_value is None:
                return

            # If no patient_id, use first patient in DB
            if not patient_id:
                patient = await self._db.users.find_one({"role": "patient"})
                if patient:
                    patient_id = str(patient["_id"])
                    age = patient.get("age", 60)
                    cornea = patient.get("cornea_thickness", 540.0)
                else:
                    return
            else:
                from bson import ObjectId
                try:
                    patient = await self._db.users.find_one({"_id": ObjectId(patient_id)})
                except Exception:
                    patient = await self._db.users.find_one({"role": "patient"})
                age = patient.get("age", 60) if patient else 60
                cornea = patient.get("cornea_thickness", 540.0) if patient else 540.0

            await self._save_and_broadcast(patient_id, iop_value, eye, age, cornea)

        except ValueError:
            pass  # Ignore non-numeric lines
        except Exception as e:
            print(f"Error processing serial line '{raw}': {e}")

    async def _save_and_broadcast(
        self,
        patient_id: str,
        iop_value: float,
        eye: str,
        age: int,
        cornea_thickness: float,
    ):
        """Save measurement to DB, run AI prediction, send alerts, broadcast via WS."""
        from services.ml_service import predict_risk

        # AI Risk Prediction
        risk_level, risk_probability = predict_risk(iop_value, age, cornea_thickness)

        measurement = {
            "patient_id": patient_id,
            "iop_value": iop_value,
            "risk_level": risk_level,
            "risk_probability": round(risk_probability, 4),
            "eye": eye,
            "timestamp": datetime.utcnow(),
            "alert_sent": False,
        }

        # Store in MongoDB
        result = await self._db.measurements.insert_one(measurement)
        measurement_id = str(result.inserted_id)

        # Trigger alerts if IOP > 21
        if iop_value > 21:
            try:
                patient = await self._db.users.find_one(
                    {"role": "patient"}
                )  # simplified lookup
                if patient and not measurement.get("alert_sent"):
                    await self.alert_service.send_high_iop_alert(
                        patient_name=patient.get("name", "Patient"),
                        patient_email=patient.get("email"),
                        iop_value=iop_value,
                        risk_level=risk_level,
                    )
                    await self._db.measurements.update_one(
                        {"_id": result.inserted_id},
                        {"$set": {"alert_sent": True}},
                    )
            except Exception as e:
                print(f"Alert error: {e}")

        # Broadcast via WebSocket
        broadcast_data = {
            "id": measurement_id,
            "patient_id": patient_id,
            "iop_value": iop_value,
            "risk_level": risk_level,
            "risk_probability": risk_probability,
            "eye": eye,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.ws_manager.broadcast_measurement(patient_id, broadcast_data)

        print(
            f"📊 IOP: {iop_value} mmHg | Risk: {risk_level} ({risk_probability:.0%}) | "
            f"Eye: {eye} | Patient: {patient_id}"
        )
