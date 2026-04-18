# 🚀 GlaucoMonitor — Quick Start

## Step 1 — Install Python 3.11 or 3.12 (if using Python 3.14)

Python 3.14 is pre-release. Some packages have wheels only for 3.11/3.12.
**Recommended: use Python 3.12.**

```bash
# Check your version
python3 --version

# macOS — install via pyenv (recommended)
brew install pyenv
pyenv install 3.12.3
pyenv local 3.12.3

# Or via conda
conda create -n glaucoma python=3.12
conda activate glaucoma
```

## Step 2 — Start MongoDB

Pick **one** option:

```bash
# Option A: Docker (easiest)
docker run -d -p 27017:27017 --name mongo mongo:7

# Option B: macOS Homebrew
brew tap mongodb/brew && brew install mongodb-community
brew services start mongodb-community

# Option C: Ubuntu/Debian
sudo apt install -y mongodb
sudo systemctl start mongodb

# Option D: Windows
# Download from https://www.mongodb.com/try/download/community
# Run as a service
```

Verify MongoDB is running:
```bash
mongosh --eval "db.adminCommand('ping')"
# should print: { ok: 1 }
```

## Step 3 — Setup Backend

```bash
cd glaucoma_monitor/backend

# Create venv with Python 3.12 specifically
python3.12 -m venv venv          # macOS/Linux
# OR
py -3.12 -m venv venv            # Windows

# Activate
source venv/bin/activate         # macOS/Linux
venv\Scripts\activate            # Windows

# Install deps
pip install --upgrade pip
pip install -r requirements.txt
```

## Step 4 — Run Backend

```bash
# Still inside backend/ with venv active
python run.py --reload
```

Expected output:
```
✅ MongoDB connected: mongodb://localhost:27017
✅ Database indexes created
🧠 Training glaucoma risk model …
✅ ML model saved
✅ Demo data seeded
📡 DEMO MODE — simulated readings every 5 s
INFO: Uvicorn running on http://0.0.0.0:8000
```

⚠️  **If port 8000 is taken**, run.py auto-picks the next free port.
    It will print the correct port — update `frontend/config.js` with it.

## Step 5 — Open Frontend

```bash
# New terminal
cd glaucoma_monitor/frontend
python3 -m http.server 3000
```

Open browser: **http://localhost:3000**

### If backend is NOT on port 8000

Edit `frontend/config.js`:
```js
const BACKEND_PORT = 8001;   // ← change to whatever port run.py printed
```

## Step 6 — Login

| Role    | Email                      | Password   |
|---------|----------------------------|------------|
| 🩺 Doctor  | doctor@glaucoma.demo    | doctor123  |
| 👤 Patient | patient@glaucoma.demo  | patient123 |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `pydantic-core` wheel build fails | Use Python 3.12, not 3.14 |
| `No module named serial_asyncio` | `pip install pyserial-asyncio` |
| `ModuleNotFoundError: fastapi` | Run `pip install -r requirements.txt` inside venv |
| MongoDB timeout on startup | Start MongoDB first (Step 2) |
| Port 8000 in use | run.py auto-selects free port; update config.js |
| `~/.zprofile brew` warning | Cosmetic only — does not affect the app |
| scikit-learn install fails on 3.14 | `pip install --pre scikit-learn` or use Python 3.12 |

---

## Verify Everything Works

- 📊 Dashboard loads with IOP chart and history table
- 💚 "Live" green dot in top-right (WebSocket connected)
- 🔄 IOP updates every 5 seconds (demo mode)
- 📥 "Download Report" button generates PDF

API docs: **http://localhost:8000/docs**
