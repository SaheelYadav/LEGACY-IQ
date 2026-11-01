"""Verification script that starts the FastAPI server and probes all M0 health endpoints."""

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
PYTHON_EXE = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
BASE_URL = "http://127.0.0.1:8015"
ENDPOINTS = [
    "/api/v1/health",
    "/api/v1/health/database",
    "/api/v1/health/redis",
    "/api/v1/health/ollama",
]


def main() -> int:
    proc = subprocess.Popen(
        [
            str(PYTHON_EXE),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8015",
        ],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        # Wait up to 8 seconds for uvicorn to bind
        ready = False
        with httpx.Client(timeout=5.0) as client:
            for _ in range(16):
                try:
                    resp = client.get(f"{BASE_URL}/api/v1/health")
                    if resp.status_code == 200:
                        ready = True
                        break
                except Exception:
                    time.sleep(0.5)

            if not ready:
                print("ERROR: FastAPI server did not become ready within timeout.")
                return 1

            for path in ENDPOINTS:
                resp = client.get(f"{BASE_URL}{path}")
                print(f"=== GET {path} -> HTTP {resp.status_code} ===")
                print(json.dumps(resp.json(), indent=2))
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())

