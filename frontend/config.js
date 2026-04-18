/**
 * GlaucoMonitor Frontend Configuration
 * 
 * If your backend is NOT on port 8000, change BACKEND_PORT below.
 * run.py prints the correct port when it starts.
 */
const BACKEND_PORT = 8000;   // ← Change this if your backend uses a different port

const API    = `http://localhost:${BACKEND_PORT}/api`;
const WS_URL = `ws://localhost:${BACKEND_PORT}/ws`;

// Save to localStorage so all pages can read it
localStorage.setItem('api_base',  API);
localStorage.setItem('ws_base',   WS_URL);