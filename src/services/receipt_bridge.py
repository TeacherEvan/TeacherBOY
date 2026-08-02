"""Receipt Bridge — Gemini text → OcrPayload → Budget Boss ingest."""

import logging
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)


def gemini_text_to_ocr_payload(text: str, country_hint: str = "TH") -> dict:
    """
    Convert Gemini vision scraped text into an OcrPayload compatible with
    Budget Boss's scraper engine (convex/lib/receipt/types.ts).

    Since Gemini returns plain text without bounding boxes, we synthesize:
    - one line per text line
    - flat confidence 85 (honest constant)
    - empty words array
    - y = ordinal index (engine only needs vertical order)
    - engine = 'gemini-vision@1' (provenance, not mislabelled as tesseract)
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    ocr_lines = []
    for idx, line_text in enumerate(lines):
        ocr_lines.append(
            {
                "text": line_text,
                "conf": 85.0,
                "y": float(idx * 100),  # arbitrary spacing, order preserved
                "words": [],  # no word-level boxes from Gemini
            }
        )

    return {
        "lines": ocr_lines,
        "width": 1024,  # synthetic; engine only uses ratios
        "height": len(lines) * 100 + 100,
        "lang": "en",
        "engine": "gemini-vision@1",
        "capturedAt": int(datetime.now(UTC).timestamp() * 1000),
        "countryHint": country_hint,
        "currencyHint": None,  # will be detected from text
    }


async def ingest_receipt(
    line_user_id: str,
    payload: dict,
    idempotency_key: str,
    timeout_seconds: float = 10.0,
) -> dict:
    """
    POST receipt payload to Budget Boss /receipts/ingest.

    Args:
        line_user_id: LINE user ID (sender of the image)
        payload: OcrPayload dict from gemini_text_to_ocr_payload
        idempotency_key: LINE message ID for deduplication
        timeout_seconds: HTTP timeout

    Returns:
        Dict with keys: success, draftId, fields, confidence, questions, error
    """
    convex_url = getattr(__import__("src.config", fromlist=["settings"]).settings, "budgetboss_convex_url", None)
    sync_token = getattr(__import__("src.config", fromlist=["settings"]).settings, "budgetboss_sync_token", None)

    if not convex_url or not sync_token:
        logger.error("BUDGETBOSS_CONVEX_URL or BUDGETBOSS_SYNC_TOKEN not configured")
        return {"success": False, "error": "Bridge not configured"}

    url = f"{convex_url.rstrip('/')}/receipts/ingest"
    headers = {
        "Authorization": f"Bearer {sync_token}",
        "Content-Type": "application/json",
    }
    body = {
        "lineUserId": line_user_id,
        "payload": payload,
        "idempotencyKey": idempotency_key,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=body)

            if response.status_code == 200:
                data = response.json()
                return {"success": True, **data}
            elif response.status_code == 401:
                logger.error("Budget Boss ingest: unauthorized (bad sync token)")
                return {"success": False, "error": "Unauthorized"}
            elif response.status_code == 404:
                logger.error("Budget Boss ingest: route not found (deploy needed)")
                return {"success": False, "error": "Route not found"}
            else:
                logger.error(f"Budget Boss ingest: {response.status_code} {response.text}")
                return {"success": False, "error": f"HTTP {response.status_code}"}

    except httpx.TimeoutException:
        logger.error("Budget Boss ingest: timeout")
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        logger.error(f"Budget Boss ingest: {e}")
        return {"success": False, "error": str(e)}


async def scan_receipt_for_app(
    image_base64: str,
    convex_user_id: str,
    idempotency_key: str,
    country_hint: str = "TH",
    timeout_seconds: float = 30.0,
) -> dict:
    """
    App camera flow: scan a receipt image on behalf of the Budget Boss app.

    Unlike the LINE path, there is no LINE user ID — the caller passes the
    Convex user ID directly. The flow is:
      1. Gemini vision on the base64 image (same RECEIPT_SCRAPE_PROMPT).
      2. gemini_text_to_ocr_payload(text, country_hint) -> OcrPayload.
      3. POST to Convex /receipts/ingest with lineUserId="app:<userId>"
         and source="app-camera".

    Returns the draft result from Convex (fields, questions, lineItems).
    """
    from src.agents.receipt_agent import RECEIPT_SCRAPE_PROMPT
    from src.utils.llm_fallback import chat_completion_with_vision_fallback

    scraped_text = await chat_completion_with_vision_fallback(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": RECEIPT_SCRAPE_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_base64}},
                ],
            }
        ],
        temperature=0.1,
        max_tokens=2000,
    )

    if not scraped_text or not scraped_text.strip():
        return {"success": False, "error": "Gemini returned no text"}

    payload = gemini_text_to_ocr_payload(scraped_text, country_hint)

    convex_url = getattr(__import__("src.config", fromlist=["settings"]).settings, "budgetboss_convex_url", None)
    sync_token = getattr(__import__("src.config", fromlist=["settings"]).settings, "budgetboss_sync_token", None)

    if not convex_url or not sync_token:
        logger.error("BUDGETBOSS_CONVEX_URL or BUDGETBOSS_SYNC_TOKEN not configured")
        return {"success": False, "error": "Bridge not configured"}

    url = f"{convex_url.rstrip('/')}/receipts/ingest"
    headers = {
        "Authorization": f"Bearer {sync_token}",
        "Content-Type": "application/json",
    }
    body = {
        "lineUserId": f"app:{convex_user_id}",
        "payload": payload,
        "idempotencyKey": idempotency_key,
        "source": "app-camera",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=body)

            if response.status_code == 200:
                return {"success": True, **response.json()}
            elif response.status_code == 401:
                logger.error("Budget Boss app ingest: unauthorized (bad sync token)")
                return {"success": False, "error": "Unauthorized"}
            elif response.status_code == 404:
                logger.error("Budget Boss app ingest: user not found")
                return {"success": False, "error": "User not found"}
            else:
                logger.error(f"Budget Boss app ingest: {response.status_code} {response.text}")
                return {"success": False, "error": f"HTTP {response.status_code}"}

    except httpx.TimeoutException:
        logger.error("Budget Boss app ingest: timeout")
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        logger.error(f"Budget Boss app ingest: {e}")
        return {"success": False, "error": str(e)}
