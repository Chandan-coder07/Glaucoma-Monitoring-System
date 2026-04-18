# 🔬 GlaucoMonitor — Glaucoma IOP Monitoring System

Real-time intraocular pressure (IOP) monitoring system connecting an ESP32 sensor to a web dashboard with AI-powered risk prediction.

---

## 📁 Project Structure

```
glaucoma_monitor/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── run.py                   # Convenience startup script
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── Procfile                 # For Railway/Render
│   ├── .env.example
│   ├── models/
│   │   └── database.py          # Pydantic models + DB init + seeding
│   ├── routers/
│   │   ├── auth.py              # POST /login, POST /register, GET /me
│   │   ├── patients.py          # GET /patients, GET /patients/:id
│   │   ├── measurements.py      # GET /history, POST /, GET /latest/:id
│   │   └── reports.py           # GET /reports/download/:id  (PDF)
│   ├── services/
│   │   ├── auth_service.py      # JWT + bcrypt
│   │   ├── serial_reader.py     # ESP32 USB serial + demo fallback
│   │   ├── websocket_manager.py # WebSocket broadcast manager
│   │   ├── alert_service.py     # Email (yagmail) + SMS (Twilio)
│   │   └── ml_service.py        # RandomForest risk prediction
│   └── ml/
│       └── glaucoma_model.pkl   # Auto-generated on first run
│
├── frontend/
│   ├── index.html               # Login page
│   ├── patient.html             # Patient dashboard
│   ├── doctor.html              # Doctor dashboard
│   └── vercel.json              # Vercel deployment config
│
├── esp32/
│   └── glaucoma_monitor.ino    # Arduino firmware for ESP32
│
├── docker-compose.yml
├── nginx.conf
└── README.md
```

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.11+
- MongoDB (local or Atlas)
- Node.js (optional, for live-reload)
- ESP32 + IOP sensor (optional — demo mode works without hardware)

### 1. Clone & Setup Backend

```bash
cd glaucoma_monitor/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your MongoDB URL, serial port, SMTP, Twilio credentials
```

### 2. Start MongoDB

Option A — Local:
```bash
mongod --dbpath /usr/local/var/mongodb
```

Option B — Docker:
```bash
docker run -d -p 27017:27017 --name mongo mongo:7.0
```

Option C — MongoDB Atlas (recommended for production): see [Atlas Setup](#mongodb-atlas-setup) below.

### 3. Run Backend

```bash
cd backend
python run.py --reload
# or directly:
uvicorn main:app --reload --port 8000
```

The backend will:
- ✅ Connect to MongoDB and create indexes
- ✅ Seed demo accounts (doctor + patient) if DB is empty
- ✅ Train the ML model on first run (saves to `ml/glaucoma_model.pkl`)
- ✅ Start serial reader (falls back to **demo mode** if ESP32 not connected)

**Demo credentials seeded automatically:**
| Role    | Email                     | Password   |
|---------|---------------------------|------------|
| Doctor  | doctor@glaucoma.demo      | doctor123  |
| Patient | patient@glaucoma.demo     | patient123 |

### 4. Serve Frontend

```bash
# Using Python's built-in server (simplest)
cd frontend
python -m http.server 3000

# Then open: http://localhost:3000
```

---

## 🔌 ESP32 Hardware Setup

### Wiring

```
ESP32 Pin 34  ──→  IOP Sensor analog output
ESP32 Pin 26  ──→  Eye selector switch (HIGH=RIGHT, LOW=LEFT)
ESP32 Pin 2   ──→  Built-in LED (status indicator)
ESP32 Pin 27  ──→  Buzzer (optional, for high IOP alert)
ESP32 GND     ──→  Sensor GND
ESP32 3.3V    ──→  Sensor VCC
```

### Sensor Compatibility
The firmware is designed for analog pressure sensors with a 0.5V–2.5V output range (e.g., Honeywell ABP series). Adjust `SENSOR_MIN_V`, `SENSOR_MAX_V`, and `IOP_MAX` constants in `glaucoma_monitor.ino` to match your sensor's datasheet.

### Uploading Firmware

1. Install [Arduino IDE](https://www.arduino.cc/en/software) or [PlatformIO](https://platformio.org/)
2. Add ESP32 board support (Espressif Systems)
3. Open `esp32/glaucoma_monitor.ino`
4. Select your board: **ESP32 Dev Module**
5. Select the correct COM/tty port
6. Upload

### Configure Serial Port in Backend

Edit `.env`:
```env
# macOS
SERIAL_PORT=/dev/tty.usbserial-XXXX

# Linux
SERIAL_PORT=/dev/ttyUSB0

# Windows
SERIAL_PORT=COM3

BAUD_RATE=9600
```

Find your port:
```bash
# macOS/Linux
ls /dev/tty.*
ls /dev/ttyUSB*

# Windows (PowerShell)
Get-WMIObject Win32_SerialPort | Select-Object Name, DeviceID
```

---

## 🧠 AI Risk Model

The `ml_service.py` trains a **RandomForestClassifier** on first startup using a synthetic but clinically-inspired dataset. It uses three features:

| Feature           | Range     | Clinical Significance                     |
|-------------------|-----------|-------------------------------------------|
| IOP (mmHg)        | 8 – 35    | Primary risk indicator                    |
| Age (years)       | 20 – 90   | Risk increases significantly over 60      |
| Cornea thickness  | 440–640 μm| Thin corneas underestimate true IOP       |

**Output risk levels:**
- 🟢 `LOW` — IOP ≤ 18 mmHg, low age/cornea risk
- 🟡 `MEDIUM` — IOP 18–24 mmHg or elevated risk factors
- 🔴 `HIGH` — IOP > 24 mmHg or multiple high-risk factors

To retrain with your own dataset (CSV with columns: `iop`, `age`, `cornea_thickness`, `risk`):
```python
# In ml_service.py, replace _generate_training_data() with:
import pandas as pd
df = pd.read_csv("your_dataset.csv")
X = df[["iop", "age", "cornea_thickness"]].values
y = df["risk"].map({"LOW": 0, "MEDIUM": 1, "HIGH": 2}).values
return X, y
```

---

## 🔔 Alert System Configuration

### Email (Gmail)

1. Enable 2FA on your Google account
2. Generate an [App Password](https://myaccount.google.com/apppasswords)
3. Set in `.env`:
```env
ALERT_EMAIL=your@gmail.com
ALERT_EMAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

### SMS (Twilio)

1. Create a [Twilio account](https://www.twilio.com)
2. Get a phone number
3. Set in `.env`:
```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+1xxxxxxxxxx
DOCTOR_PHONE_NUMBER=+1xxxxxxxxxx
```

Alerts fire when `IOP > 21 mmHg`, with a 30-minute cooldown per patient to prevent spam.

---

## 📄 PDF Report

Doctors and patients can download a PDF report via:
```
GET /api/reports/download/{patient_id}?days=30
Authorization: Bearer <token>
```

The report includes:
- Patient demographics
- Summary statistics (avg, max, min IOP)
- Risk distribution (LOW / MEDIUM / HIGH counts)
- Full measurement history table (up to 50 entries)

---

## 🔐 Authentication

JWT tokens are issued at login and must be included in all API requests:

```javascript
headers: { "Authorization": "Bearer <token>" }
```

Token validity: **24 hours**

### Role Permissions

| Endpoint                          | Doctor | Patient |
|-----------------------------------|--------|---------|
| `GET /api/patients/`              | ✅     | ❌      |
| `GET /api/patients/:id`           | ✅     | Own only|
| `GET /api/measurements/history`   | ✅     | Own only|
| `GET /api/reports/download/:id`   | ✅     | Own only|
| `WebSocket /ws/all`               | ✅     | ❌      |
| `WebSocket /ws/:patient_id`       | ✅     | Own only|

---

## 🌐 WebSocket Protocol

Connect: `ws://localhost:8000/ws/{patient_id}`
- Patients: use their own `user_id`
- Doctors: use `"all"` to receive all patient updates

**Incoming message format:**
```json
{
  "type": "new_measurement",
  "data": {
    "id": "664a1b2c3d4e5f6a7b8c9d0e",
    "patient_id": "664a1b2c3d4e5f6a7b8c9d01",
    "iop_value": 22.3,
    "risk_level": "HIGH",
    "risk_probability": 0.87,
    "eye": "RIGHT",
    "timestamp": "2024-05-20T14:32:10.123456"
  }
}
```

**Keep-alive:**
```
Client → Server: "ping"
Server → Client: {"type": "pong"}
```

---

## ☁️ Deployment

### MongoDB Atlas Setup

1. Go to [cloud.mongodb.com](https://cloud.mongodb.com) → Create free cluster
2. Create a database user (username + password)
3. Whitelist IP `0.0.0.0/0` (or your server IP)
4. Get connection string:
   ```
   mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/glaucoma_monitor
   ```
5. Set `MONGO_URL` in your deployment environment

---

### Backend — Railway.app

1. Push backend to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select the `backend/` folder
4. Add environment variables (from `.env.example`)
5. Railway auto-detects `Procfile` and deploys

Your backend URL will be: `https://glaucoma-backend.railway.app`

---

### Backend — Render.com

1. New Web Service → Connect GitHub repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables
5. Deploy

---

### Frontend — Vercel

1. Edit `frontend/vercel.json` — replace `your-backend.railway.app` with your actual backend URL
2. Push `frontend/` to GitHub
3. Go to [vercel.com](https://vercel.com) → New Project → Import repo
4. Set root directory to `frontend/`
5. Deploy

---

### Frontend — Netlify

```bash
# Install Netlify CLI
npm install -g netlify-cli

cd frontend
netlify deploy --prod --dir .
```

Create `frontend/_redirects`:
```
/api/*  https://your-backend.railway.app/api/:splat  200
```

---

### Docker Compose (Self-hosted)

```bash
# Copy and configure environment
cp backend/.env.example .env
# Edit .env with your values

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop
docker-compose down
```

Access:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## 🧪 Testing the System

### Test without ESP32 (Demo Mode)

The backend automatically falls back to **demo mode** when no serial port is available. It simulates ESP32 readings every 5 seconds with realistic IOP values including occasional highs to trigger alerts.

### Manual Measurement Entry

```bash
curl -X POST http://localhost:8000/api/measurements/ \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{"patient_id": "<patient_id>", "iop_value": 24.5, "eye": "RIGHT"}'
```

### Test High IOP Alert

```bash
# Use the manual entry above with iop_value > 21
# If email/SMS credentials are configured, alerts will fire
# Otherwise, check backend console for: 🚨 [ALERT] High IOP detected...
```

### Serial Port Simulation (without ESP32)

```python
# Install: pip install pyserial
import serial
import time
import random

# Connect to a virtual serial port (use socat on macOS/Linux)
# socat -d -d pty,raw,echo=0 pty,raw,echo=0
# This creates two linked virtual ports, e.g., /dev/pts/3 and /dev/pts/4

port = serial.Serial('/dev/pts/3', 9600)
while True:
    iop = round(random.uniform(15, 26), 1)
    msg = f"IOP:{iop},EYE:RIGHT,PATIENT:default\n"
    port.write(msg.encode())
    print(f"Sent: {msg.strip()}")
    time.sleep(5)
```

---

## 🛡️ Security Checklist for Production

- [ ] Change `JWT_SECRET_KEY` to a long random string (32+ chars)
- [ ] Restrict CORS `allow_origins` to your frontend domain
- [ ] Use MongoDB Atlas with strong password + IP whitelist
- [ ] Use Gmail App Password (never your real password)
- [ ] Enable HTTPS on all deployments (Vercel/Railway handle this automatically)
- [ ] Set `DEBUG=False` / remove `--reload` flag
- [ ] Use environment secrets manager (Railway Secrets, Vercel Environment Variables)
- [ ] Rate-limit the `/api/auth/login` endpoint in production

---

## 📊 API Reference

```
POST   /api/auth/register     - Register new user
POST   /api/auth/login        - Get JWT token
GET    /api/auth/me           - Current user profile

GET    /api/patients/         - List all patients (doctor)
GET    /api/patients/:id      - Patient profile + medicines
PUT    /api/patients/medicines/:id/taken  - Mark medicine taken

GET    /api/measurements/history          - IOP history (with filters)
POST   /api/measurements/               - Manual measurement
GET    /api/measurements/latest/:id     - Latest IOP reading

GET    /api/reports/download/:id        - Download PDF report

WS     /ws/:patient_id                  - Real-time IOP stream
GET    /health                          - System health check
GET    /docs                            - Interactive API docs (Swagger)
```

---

## ⚠️ Medical Disclaimer

This software is for **research and educational purposes only**. It is NOT a certified medical device and must NOT be used for clinical diagnosis or treatment decisions. Always consult a qualified ophthalmologist for glaucoma diagnosis and management.
