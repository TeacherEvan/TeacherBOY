"""External Vision API router."""
import asyncio
import base64
import binascii
import hmac
import logging
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.config import settings
from src.services.external_vision_service import SUPPORTED_TASKS, analyze_image_task
from src.utils.ip_rate_limiter import IpRateLimiter
from src.utils.ssrf_guard import DEFAULT_ALLOWED_HOSTS, safe_fetch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["External Vision API"])
_limiter = IpRateLimiter(max_requests=30, window_seconds=60)

def _api_enabled() -> bool: return settings.external_api_enabled
def _expected_token() -> str | None: return settings.get_external_api_token()
def _rate_limit_per_minute() -> int: return settings.external_api_rate_limit_per_minute
def _max_image_bytes() -> int: return int(settings.external_api_max_image_mb * 1024 * 1024)
def _timeout_seconds() -> float: return settings.external_api_timeout_seconds
def _extra_image_hosts() -> set[str]: return settings.get_external_api_image_hosts()
def _vision_providers_configured() -> bool: return settings.is_any_vision_provider_configured()

class ImageInput(BaseModel):
    dataUrl: str | None = None; base64: str | None = None; url: str | None = None
class AnalyzeRequest(BaseModel):
    image: ImageInput; task: str = "general"; prompt: str | None = None; countryHint: str = "TH"

def _require_auth(request: Request) -> None:
    if not _api_enabled(): raise HTTPException(status_code=503, detail="External API disabled")
    token = _expected_token()
    if not token: raise HTTPException(status_code=503, detail="External API not configured")
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or not hmac.compare_digest(header[7:], token):
        raise HTTPException(status_code=401, detail="Unauthorized")

def _check_rate_limit(request: Request) -> None:
    _limiter.max_requests = _rate_limit_per_minute()
    ip = request.client.host if request.client else "unknown"
    if not _limiter.allow(ip): raise HTTPException(status_code=429, detail="Rate limit exceeded")

@router.get("/tasks")
async def list_tasks(request: Request) -> dict:
    _require_auth(request)
    return {"tasks": list(SUPPORTED_TASKS), "rate_limit_per_minute": _rate_limit_per_minute()}

@router.post("/analyze")
async def analyze(request: Request, body: AnalyzeRequest) -> dict:
    _require_auth(request); _check_rate_limit(request)
    if body.task not in SUPPORTED_TASKS:
        raise HTTPException(status_code=422, detail=f"Unsupported task '{body.task}'")
    if not _vision_providers_configured():
        raise HTTPException(status_code=503, detail="No vision provider configured")
    request_id = uuid.uuid4().hex[:16]
    logger.info(f"🌐 /api/v1/analyze task={body.task} request_id={request_id}")
    result = await analyze_image_task(image_data_url="data:image/png;base64,abc", task=body.task, prompt=body.prompt, country_hint=body.countryHint)
    return {"success": True, "requestId": request_id, **result}
