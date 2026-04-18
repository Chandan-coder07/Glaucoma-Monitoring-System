"""
WebSocket Connection Manager.
Manages active WebSocket connections and broadcasts IOP data to clients.
"""

import json
from typing import Dict, List
from fastapi import WebSocket


class WebSocketManager:
    """
    Manages WebSocket connections grouped by patient_id.
    Doctors can subscribe to "all" to receive all patient data.
    """

    def __init__(self):
        # patient_id -> list of connected websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, patient_id: str):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        if patient_id not in self.active_connections:
            self.active_connections[patient_id] = []
        self.active_connections[patient_id].append(websocket)
        print(f"🔌 WebSocket connected: patient_id={patient_id} | Total connections: {self.total_connections}")

    def disconnect(self, websocket: WebSocket, patient_id: str):
        """Remove a WebSocket connection."""
        if patient_id in self.active_connections:
            self.active_connections[patient_id].remove(websocket)
            if not self.active_connections[patient_id]:
                del self.active_connections[patient_id]

    @property
    def total_connections(self) -> int:
        return sum(len(conns) for conns in self.active_connections.values())

    async def broadcast_to_patient(self, patient_id: str, data: dict):
        """Send data to all connections for a specific patient."""
        if patient_id in self.active_connections:
            dead_connections = []
            message = json.dumps(data)
            for websocket in self.active_connections[patient_id]:
                try:
                    await websocket.send_text(message)
                except Exception:
                    dead_connections.append(websocket)
            # Clean up dead connections
            for ws in dead_connections:
                self.active_connections[patient_id].remove(ws)

    async def broadcast_to_doctors(self, data: dict):
        """
        Broadcast data to all doctor connections (subscribed under "all").
        Doctors connect via /ws/all to see all patient data.
        """
        await self.broadcast_to_patient("all", data)

    async def broadcast_measurement(self, patient_id: str, measurement: dict):
        """
        Broadcast a new IOP measurement to:
        1. The specific patient
        2. All doctors (subscribed to "all")
        """
        payload = {
            "type": "new_measurement",
            "data": measurement,
        }
        await self.broadcast_to_patient(patient_id, payload)
        await self.broadcast_to_doctors({**payload, "patient_id": patient_id})
