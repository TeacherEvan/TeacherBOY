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

# System prompt for structured journal extraction
DEBRIEF_EXTRACTION_PROMPT = """You are a teaching assistant analyzing a daily journal image. 
Extract the following fields STRICTLY as a valid JSON object. Do not include markdown formatting or explanations.
Fields:
- "timePeriod": (string) e.g., "9h12 - 10h10, Period 3" or null if not found
- "subject": (string) e.g., "English - foreign languages" or null
- "lesson": (string) e.g., "Phonics" or null
- "teacher": (string) e.g., "Teacher Evan" or null
- "observations": (string) A 2-3 sentence summary of what the students did/learned, or null

If a field cannot be determined from the image, use null. Return ONLY the JSON object."""


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

    async def extract_from_image(self, image_url_or_base64: str, chat_id: str, date_str: str) -> dict[str, Any]:
        """
        Extracts structured debrief data from an image.
        Falls back to local OCR if LLM vision fails to return valid JSON.
        Cross-validates with Google Calendar via Maton API if teacher/subject is missing.
        """
        if not self.llm_vision_fn:
            raise RuntimeError("DebriefExtractionService.llm_vision_fn is not configured.")

        # 1. Initial LLM Vision Extraction
        messages = [
            {"role": "system", "content": DEBRIEF_EXTRACTION_PROMPT + " \n\nReturn ONLY valid JSON."},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image_url_or_base64}}]},
        ]

        raw_response = await self.llm_vision_fn(messages, max_tokens=500, temperature=0.1)
        extracted_data = self._parse_json_response(raw_response)

        # 2. Local OCR Fallback (if LLM returned empty or invalid JSON) - Run in thread to avoid blocking
        if not extracted_data.get("observations"):
            logger.info("LLM extraction weak, attempting local OCR fallback in background thread...")
            ocr_text = await asyncio.to_thread(self._run_local_ocr_sync, image_url_or_base64)
            if ocr_text:
                messages[1]["content"] = f"OCR detected this text in the image: {ocr_text}\n\nNow extract the JSON fields:"
                raw_response = await self.llm_vision_fn(messages, max_tokens=500, temperature=0.1)
                extracted_data = self._parse_json_response(raw_response)

        # 3. Maton API Cross-Validation
        validated = False
        if (not extracted_data.get("teacher") or not extracted_data.get("subject")) and extracted_data.get("timePeriod"):
            calendar_match = await self._validate_with_maton_calendar(date_str, extracted_data.get("timePeriod"), chat_id)
            if calendar_match:
                extracted_data["teacher"] = calendar_match.get("teacher") or extracted_data.get("teacher")
                extracted_data["subject"] = calendar_match.get("subject") or extracted_data.get("subject")
                validated = True
                logger.info("Maton API successfully validated/filled missing debrief fields.")

        return {**extracted_data, "validatedByCalendar": validated}

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
