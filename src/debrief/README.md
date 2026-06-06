# Ms Green Debrief Orchestrator

This folder contains a standalone FastAPI app for the separate
“Ms Green debrief” instance.

## Run locally
python -m uvicorn src.debrief.main:app --host 0.0.0.0 --port 8001

## Run as systemd service
See misc/systemd/ for the service template.
