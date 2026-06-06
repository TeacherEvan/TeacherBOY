"""
Minimal separate FastAPI instance to orchestrate Ms Green debrief sessions.

Run:
    uvicorn src.debrief.main:app --host 0.0.0.0 --port 8001

Environment:
    HERMES_BASE_URL=https://inference-api.nousresearch.com/v1
    HERMES_API_KEY=...
    HERMES_MODEL=...
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Ms Green Debrief Orchestrator")


@app.get("/health")
async def healthcheck() -> dict:
    return {"status": "ok"}


@app.post("/debrief")
async def trigger_debrief(payload: dict) -> dict:
    return {
        "status": "queued",
        "received": payload,
    }
