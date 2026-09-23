"""External vision service — task registry, JSON parsing, receipt bridge reuse."""

import asyncio
import json
import logging
import re
import time
from typing import Any

from src.agents.receipt_agent import RECEIPT_SCRAPE_PROMPT
from src.services.receipt_bridge import gemini_text_to_ocr_payload
from src.utils.llm_fallback import chat_completion_with_vision_fallback_ex

logger = logging.getLogger(__name__)

TASK_RECEIPT = "receipt"
TASK_ARTICLE = "article"
TASK_NEWS = "news"
TASK_OCR = "ocr"
TASK_GENERAL = "general"

SUPPORTED_TASKS: tuple[str, ...] = (
    TASK_RECEIPT,
    TASK_ARTICLE,
    TASK_NEWS,
    TASK_OCR,
    TASK_GENERAL,
)

OCR_PROMPT = (
    "Extract ALL text from this image. Return ONLY the text content found in the image. "
    "Include any text from signs, documents, receipts, screens, menus, labels, handwriting, etc. "
    "Preserve line breaks and layout as much as possible. "
    "If multiple languages are present, include all. "
    "Do not add explanations or analysis - just the extracted text."
)

ARTICLE_PROMPT = (
    'You are reading an image of an article, clipping, or document. '
    'Return STRICT JSON only (no prose, no code fences) with keys: '
    '"title" (string), "publication" (string or null), "date" (ISO date or null), '
    '"byline" (string or null), "summary" (string, max 120 words), '
    '"key_points" (array of 3-6 short strings), "language" (short code like "en" or "th"). '
    'If a field is not visible, use null and do not guess.'
)

NEWS_PROMPT = (
    "You are reading an image of a news item (screenshot, clipping, or page). "
    "Return STRICT JSON only (no prose, no code fences) with keys: "
    '"headline" (string), "source" (string or null), "date" (ISO date or null), '
    '"top_facts" (array of 3-6 short strings), "why_it_matters" (string, max 60 words), '
    '"entities" (object with "people", "organizations", "locations" arrays), "language" (short code). '
    "Only include facts visible in the image; never speculate."
)

GENERAL_PROMPT = (
    "Describe this image accurately and answer any question the caller included. "
    "Be literal and factual; state uncertainty instead of guessing."
)

_TASK_PROMPTS: dict[str, str] = {
    TASK_OCR: OCR_PROMPT,
    TASK_RECEIPT: RECEIPT_SCRAPE_PROMPT,
    TASK_ARTICLE: ARTICLE_PROMPT,
    TASK_NEWS: NEWS_PROMPT,
    TASK_GENERAL: GENERAL_PROMPT,
}

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def build_task_prompt(task: str, custom_prompt: str | None) -> str:
    if custom_prompt and custom_prompt.strip():
        return custom_prompt.strip()
    if task not in _TASK_PROMPTS:
        raise ValueError(f"Unsupported task: {task}")
    return _TASK_PROMPTS[task]


def parse_structured_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = candidate.removeprefix("json").strip()
    match = _JSON_BLOCK_RE.search(candidate)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def analyze_image_task(
    *,
    image_data_url: str,
    task: str,
    prompt: str | None = None,
    country_hint: str = "TH",
    max_tokens: int = 2000,
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    effective_prompt = build_task_prompt(task, prompt)
    started = time.monotonic()
    result = None
    try:
        result = await asyncio.wait_for(
            chat_completion_with_vision_fallback_ex(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": effective_prompt},
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                        ],
                    }
                ],
                temperature=0.1 if task in (TASK_OCR, TASK_RECEIPT) else 0.2,
                max_tokens=max_tokens,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise RuntimeError(f"Vision analysis timed out after {timeout_seconds}s")
    latency_ms = int((time.monotonic() - started) * 1000)
    if result is None:
        raise RuntimeError("All vision providers failed")
    text, provider = result
    payload: dict[str, Any] = {
        "task": task,
        "text": text,
        "structured": None,
        "ocr": None,
        "provider": provider,
        "latency_ms": latency_ms,
    }
    if task == TASK_RECEIPT:
        payload["ocr"] = gemini_text_to_ocr_payload(text, country_hint)
    elif task in (TASK_ARTICLE, TASK_NEWS):
        payload["structured"] = parse_structured_json(text)
    return payload
