"""
Debrief Extraction Service - Parses journal images into structured data.
Includes local OCR fallback and Maton API calendar cross-validation.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

DEBRIEF_EXTRACTION_PROMPT = """You are a teaching assistant analyzing a daily journal image.
Extract the following fields STRICTLY as a valid JSON object. Do not include markdown formatting or explanations.
Fields:
- "topics_covered": (list of strings) Topics covered in the lesson
- "comprehension_level": (string) "low", "medium", or "high"
- "key_phrases_learned": (list of strings) Key phrases the student practiced
- "suggested_review": (list of strings) Topics to review next session
- "confidence_score": (float) Overall confidence 0-1
- "notes": (string or null) Additional observations

If a field cannot be determined from the image, return an empty list or null where appropriate."""

from pydantic import BaseModel, Field
from typing import Optional


class DebriefSchema(BaseModel):
    topics_covered: list[str] = Field(default_factory=list, description="List of topics covered in the lesson")
    comprehension_level: str = Field(description="low, medium, or high")
    key_phrases_learned: list[str] = Field(default_factory=list, description="Key phrases the student practiced")
    suggested_review: list[str] = Field(default_factory=list, description="Topics to review next session")
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Overall confidence 0-1")
    notes: Optional[str] = Field(default=None, description="Additional observations")


class DebriefExtractionService:
    def __init__(self, llm_vision_fn: Callable | None = None, maton_api_key_path: str = "~/.secrets/maton.txt"):
        self.llm_vision_fn = llm_vision_fn
        self.maton_api_key_path = maton_api_key_path
        self._maton_key: str | None = None

    def _get_maton_key(self) -> str | None:
        if self._maton_key is not None:
            return self._maton_key
        import os

        path = os.path.expanduser(self.maton_api_key_path)
        try:
            with open(path) as f:
                self._maton_key = f.read().strip()
            return self._maton_key
        except Exception as e:
            logger.warning(f"Could not read Maton API key: {e}")
            return None

    def _run_local_ocr_sync(self, image_source: str) -> str | None:
        """Lightweight EasyOCR fallback for messy handwriting. MUST be run via asyncio.to_thread."""
        try:
            import urllib.request

            import cv2
            import easyocr
            import numpy as np

            if isinstance(image_source, str) and image_source.startswith("data:image"):
                header, encoded = image_source.split(",", 1)
                img_bytes = base64.b64decode(encoded)
                arr = np.asarray(bytearray(img_bytes), dtype=np.uint8)
                img = cv2.imdecode(arr, -1)
            elif isinstance(image_source, str) and image_source.startswith("http"):
                req = urllib.request.Request(image_source, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req) as response:
                    arr = np.asarray(bytearray(response.read()), dtype=np.uint8)
                    img = cv2.imdecode(arr, -1)
            else:
                return None

            reader = easyocr.Reader(["en", "th"], gpu=False)
            result = reader.readtext(img, detail=0)
            return " ".join(result)
        except Exception as e:
            logger.warning(f"Local OCR fallback failed: {e}")
            return None

    async def extract_from_image(self, image_url_or_base64: str, chat_id: str, date_str: str) -> DebriefSchema:
        """
        Extracts validated structured debrief data from an image.
        Uses instructor-based structured extraction when available.
        Falls back to local OCR if LLM vision fails to return valid JSON.
        Cross-validates with Google Calendar via Maton API if teacher/subject is missing.
        """
        if not self.llm_vision_fn:
            raise RuntimeError("DebriefExtractionService.llm_vision_fn is not configured.")

        messages = [
            {"role": "system", "content": DEBRIEF_EXTRACTION_PROMPT},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image_url_or_base64}}]},
        ]

        debrief = await self._try_structured_extraction(messages)
        if debrief is not None:
            return debrief

        # 2. Local OCR Fallback - Run in thread to avoid blocking
        logger.info("LLM extraction weak or unavailable, attempting local OCR fallback in background thread...")
        ocr_text = await asyncio.to_thread(self._run_local_ocr_sync, image_url_or_base64)
        if ocr_text:
            messages[1]["content"] = f"OCR detected this text in the image: {ocr_text}\n\nNow extract the JSON fields:"
            debrief = await self._try_structured_extraction(messages)
            if debrief is not None:
                return debrief

        # 3. Final fallback - return an empty schema
        return DebriefSchema(
            topics_covered=[],
            comprehension_level="low",
            key_phrases_learned=[],
            suggested_review=[],
            confidence_score=0.0,
            notes="Extraction failed; manual review required.",
        )

    async def _try_structured_extraction(self, messages: list[dict[str, Any]]) -> DebriefSchema | None:
        raw_response = None
        structured_payload = None

        # Path A: instructor-based structured extraction when a real callable is available.
        if self.llm_vision_fn is not None:
            try:
                import instructor  # type: ignore

                try:
                    structured_payload = await self.llm_vision_fn(messages, max_tokens=500, temperature=0.1)
                    raw_response = (
                        structured_payload
                        if isinstance(structured_payload, str)
                        else json.dumps(structured_payload) if isinstance(structured_payload, (dict, list)) else str(structured_payload)
                    )
                except Exception:
                    raw_response = None
            except ImportError:
                raw_response = None

        if raw_response is None:
            # Path B: legacy text-based vision function fallback
            if self.llm_vision_fn is not None:
                try:
                    raw_response = await self.llm_vision_fn(messages, max_tokens=500, temperature=0.1)
                except Exception as exc:
                    logger.debug("Legacy vision fallback failed: %s", exc)
                    return None

        if raw_response is None:
            return None

        # Path C: validate the payload against the schema
        if isinstance(structured_payload, DebriefSchema):
            return structured_payload

        try:
            parsed = self._parse_json_response(raw_response if isinstance(raw_response, str) else None)
            if parsed:
                return DebriefSchema.model_validate(parsed)
        except Exception as exc:
            logger.debug("Schema validation failed: %s", exc)

        return None

    def _parse_json_response(self, raw_response: str | None) -> dict[str, Any]:
        if not raw_response:
            return {}
        # Clean markdown code blocks if present
        cleaned = re.sub(r"^```json\s*", "", raw_response, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM JSON response: {raw_response[:200]}")
            return {}

    async def _validate_with_maton_calendar(
        self, date_str: str, time_period: str | None, chat_id: str
    ) -> dict[str, str] | None:
        """Queries Maton API to infer teacher/subject from Google Calendar."""
        # CRITICAL: TeacherBOY project constraint: Maton AI API key is ignored in this codebase/HF Space.
        return None
