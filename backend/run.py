"""
GlaucoMonitor backend launcher.
Picks a free port automatically to avoid port-conflict errors.

Usage:
    python run.py                # auto port
    python run.py --port 8000   # specific port
    python run.py --reload      # dev mode with auto-reload
"""
import argparse
import os
import socket
import sys

# Load .env BEFORE importing anything that reads env vars
from dotenv import load_dotenv
load_dotenv()


def find_free_port(start: int = 8000, attempts: int = 20) -> int:
    """Find a free TCP port starting from `start`."""
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}–{start + attempts}")


def main():
    parser = argparse.ArgumentParser(description="GlaucoMonitor Backend")
    parser.add_argument("--host",   default="0.0.0.0")
    parser.add_argument("--port",   type=int, default=0,
                        help="Port (0 = auto-detect free port, default: 8000)")
    parser.add_argument("--reload", action="store_true",
                        help="Enable hot-reload (dev mode)")
    args = parser.parse_args()

    # Resolve port
    port = args.port if args.port else find_free_port(8000)

    print("=" * 55)
    print("  GlaucoMonitor Backend")
    print("=" * 55)
    print(f"  URL       : http://{args.host}:{port}")
    print(f"  Docs      : http://localhost:{port}/docs")
    print(f"  MongoDB   : {os.getenv('MONGO_URL', 'mongodb://localhost:27017')}")
    print(f"  Serial    : {os.getenv('SERIAL_PORT', '(demo mode)')}")
    print(f"  Reload    : {args.reload}")
    print("=" * 55)
    print()
    print("  Demo login:")
    print("    Doctor  → doctor@glaucoma.demo  / doctor123")
    print("    Patient → patient@glaucoma.demo / patient123")
    print()

    # ── Update frontend API URL hint ──────────────────────────────────────────
    if port != 8000:
        print(f"  ⚠️  Backend is on port {port} (not 8000).")
        print(f"     Open frontend/index.html and change:")
        print(f"       const API = 'http://localhost:8000/api'")
        print(f"     to:")
        print(f"       const API = 'http://localhost:{port}/api'")
        print()

    import uvicorn
    uvicorn.run(
        "main:app",
        host=args.host,
        port=port,
        reload=args.reload,
        workers=1,               # Must be 1 when using reload or in-process state
        log_level="info",
        ws_ping_interval=20,
        ws_ping_timeout=30,
    )


if __name__ == "__main__":
    main()
