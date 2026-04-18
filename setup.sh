#!/bin/bash
# ── GlaucoMonitor One-Click Setup ────────────────────────────────────────────
set -e
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   GlaucoMonitor Setup                   ║"
echo "╚══════════════════════════════════════════╝"
echo ""

cd "$(dirname "$0")/backend"

# 1. Create venv if missing
if [ ! -d "venv" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv venv
fi

# 2. Activate
source venv/bin/activate

# 3. Upgrade pip silently
pip install --upgrade pip setuptools wheel -q

# 4. Install dependencies
echo "→ Installing dependencies (this may take 2-3 minutes)..."
pip install -r requirements.txt -q

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the backend:"
echo "   cd backend && source venv/bin/activate && python run.py --reload"
echo ""
echo "To start the frontend (new terminal):"
echo "   cd frontend && python3 -m http.server 3000"
echo ""
echo "Then open: http://localhost:3000"
echo ""
echo "Demo login:"
echo "   Doctor:  doctor@glaucoma.demo / doctor123"
echo "   Patient: patient@glaucoma.demo / patient123"
