"""
Date Extraction Service - AI-powered date extraction from message text.

This service uses GPT-4o to extract dates and event descriptions from
natural language text messages. Designed for the "Zeus Scrape" feature
that allows users to retrospectively add calendar events from chat history.

Features:
- Extracts multiple dates from a batch of messages
- Identifies event titles/descriptions from context
- Handles various date formats (relative, absolute, Thai, English)
- Deduplication of similar events
- Confidence scoring for extractions

Architecture:
- Uses GitHub Models Service (GPT-4o) for AI extraction
- Returns structured data ready for CalendarSessionManager
- Thread-safe and async-compatible
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

# Extraction prompt template - simplified to reduce AI refusals
EXTRACTION_PROMPT = """You are a date finder for calendar events.

Messages:
{messages}

Today: {today}
Current year: {year}
Next year: {next_year}

Find dates and events in the messages. Handle English and Thai dates (relative like "tomorrow"/"พรุ่งนี้", "next week"/"สัปดาห์หน้า", and absolute formats).

Rules:
- Use numeric years only ({year} or {next_year})
- Date format: YYYY-MM-DD (e.g., {year}-01-15)
- Skip past dates (before today)
- If year not specified, use {year} for future dates, {next_year} if already passed this year
- Return ONLY a JSON array, nothing else
- Empty array [] if no dates found

JSON format:
[{{"date":"{year}-01-15","title":"Event title","description":"Optional details","source_text":"Original message","confidence":"high"}}]

Confidence: "high", "medium", or "low"."""


@dataclass
class ExtractedEvent:
    """Represents a single extracted event."""

    event_date: date
    title: str
    description: str
    source_text: str
    confidence: str  # high, medium, low

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for session manager."""
        return {
            "date": self.event_date,
            "title": self.title,
            "description": self.description,
            "source_text": self.source_text,
            "confidence": self.confidence,
        }


class DateExtractionService:
    """
    Service for extracting calendar events from message text using AI.

    Uses GPT-4o via GitHub Models Service for natural language understanding
    of dates and events in both English and Thai.
    """

    def __init__(self):
        """Initialize the date extraction service."""
        self._extraction_count = 0
        logger.info("📅 DateExtractionService initialized")

    async def extract_events_from_messages(
        self,
        messages: list[str],
        max_events: int = 10,
    ) -> list[ExtractedEvent]:
        """
        Extract calendar events from a list of message texts.

        Args:
            messages: List of message text strings to analyze
            max_events: Maximum number of events to extract

        Returns:
            List of ExtractedEvent objects
        """
        from src.services.metrics_service import metrics_service

        if not messages:
            logger.debug("📅 No messages to extract from")
            return []

        # Format messages for prompt
        numbered_messages = "\n".join(f"{i + 1}. {msg}" for i, msg in enumerate(messages))

        today = datetime.now(BANGKOK_TZ).date()
        current_year = today.year
        prompt = EXTRACTION_PROMPT.format(
            messages=numbered_messages,
            today=today.isoformat(),
            year=current_year,
            next_year=current_year + 1,
        )

        try:
            from src.services.ai_review_service import ai_review_service

            response = await ai_review_service.extract_calendar_candidates([prompt])

            if not response:
                logger.warning("📅 No response from AI, using fallback extraction")
                events = self._fallback_extraction(messages, today)
                metrics_service.record_extraction_request(
                    provider=None, success=False, used_fallback=True
                )
                return events

            # Prepend Godmode prefill for Gemini (response may be completion only)
            prefill = '[{"date":"'
            if not response.lstrip().startswith("["):
                response = prefill + response

            # Parse JSON response
            events = self._parse_extraction_response(response, today)

            # Deduplicate and limit
            events = self._deduplicate_events(events)[:max_events]

            self._extraction_count += 1
            logger.info(f"📅 Extracted {len(events)} events from {len(messages)} messages")
            metrics_service.record_extraction_request(
                provider="gemini", success=True, event_count=len(events)
            )
            return events

        except Exception as e:
            logger.error(f"📅 AI extraction failed: {e}", exc_info=True)
            events = self._fallback_extraction(messages, today)
            metrics_service.record_extraction_request(
                provider="gemini", success=False, used_fallback=True
            )
            return events

    def _parse_extraction_response(
        self,
        response: str,
        today: date,
    ) -> list[ExtractedEvent]:
        """
        Parse the AI response into ExtractedEvent objects.

        Args:
            response: JSON string from AI
            today: Today's date for validation

        Returns:
            List of ExtractedEvent objects
        """
        events = []

        try:
            # Clean response (remove markdown code blocks and extra whitespace)
            cleaned = response.strip()

            # Remove markdown code blocks if present
            if "```" in cleaned:
                # Extract content between code blocks
                match = re.search(r"```(?:json)?\s*\n?(.+?)```", cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1).strip()
                else:
                    # Try removing just the markers
                    cleaned = re.sub(r"```(?:json)?\s*\n?", "", cleaned)
                    cleaned = re.sub(r"\s*```\s*$", "", cleaned)

            # Try to extract JSON array if embedded in text
            if not cleaned.startswith("["):
                json_match = re.search(r"\[.+\]", cleaned, re.DOTALL)
                if json_match:
                    cleaned = json_match.group(0)
                else:
                    logger.warning(f"📅 Response doesn't contain JSON array: {cleaned[:100]}")
                    return []

            data = json.loads(cleaned)

            if not isinstance(data, list):
                logger.warning("📅 AI response is not a list")
                return []

            for item in data:
                try:
                    # Parse date
                    date_str = item.get("date", "")

                    # Validate date string format and check for placeholders
                    if not date_str or "YYYY" in date_str or "MM" in date_str or "DD" in date_str:
                        logger.warning(f"📅 Invalid date format with placeholders: {date_str}")
                        continue

                    try:
                        event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    except ValueError as e:
                        logger.warning(f"📅 Could not parse date '{date_str}': {e}")
                        # Try alternative parsing with dateparser as fallback
                        try:
                            import dateparser

                            dt = dateparser.parse(date_str)
                            if dt:
                                event_date = dt.date()
                            else:
                                continue
                        except Exception:
                            continue

                    # Validate year is reasonable (not 1900 or 9999, etc.)
                    current_year = today.year
                    if event_date.year < current_year or event_date.year > current_year + 5:
                        logger.warning(f"📅 Date year {event_date.year} is out of reasonable range")
                        continue

                    # Skip past dates
                    if event_date < today:
                        logger.debug(f"📅 Skipping past date: {event_date}")
                        continue

                    # Create event
                    event = ExtractedEvent(
                        event_date=event_date,
                        title=str(item.get("title", "Event"))[:50],
                        description=str(item.get("description", ""))[:200],
                        source_text=str(item.get("source_text", ""))[:100],
                        confidence=item.get("confidence", "medium"),
                    )
                    events.append(event)

                except Exception as e:
                    logger.debug(f"📅 Error parsing event item: {e}")
                    continue

        except json.JSONDecodeError as e:
            logger.warning(f"📅 Failed to parse AI response as JSON: {e}")
            logger.debug(f"📅 Raw response: {response[:500]}")

        return events

    def _fallback_extraction(
        self,
        messages: list[str],
        today: date,
    ) -> list[ExtractedEvent]:
        """
        Simple regex-based fallback extraction when AI is unavailable.

        Args:
            messages: List of message texts
            today: Today's date

        Returns:
            List of ExtractedEvent objects
        """
        events = []

        # Best-effort: use dateparser when available for richer relative parsing
        # (e.g., "Friday", "next Friday", Thai relative phrases).
        dateparser_parse = None
        try:
            import importlib

            dateparser = importlib.import_module("dateparser")
            dateparser_parse = getattr(dateparser, "parse", None)
        except Exception:
            dateparser_parse = None

        # Heuristic: only attempt extraction when text looks event-like.
        # This reduces false positives significantly.
        event_keywords = [
            "meeting",
            "call",
            "appointment",
            "deadline",
            "due",
            "schedule",
            "remind",
            "reminder",
            "party",
            "event",
            "interview",
            "class",
            "exam",
            "conference",
            "workshop",
            "training",
            "session",
            "lunch",
            "dinner",
            "breakfast",
            "dear all",  # Common meeting announcement pattern
            "everyone",
            "team",
            "ประชุม",
            "นัด",
            "เดดไลน์",
            "กำหนดส่ง",
            "ส่งงาน",
            "สัมภาษณ์",
            "สอบ",
            "เรียน",
        ]

        # Simple patterns to match (cheap and reliable)
        patterns = [
            # "tomorrow" or "พรุ่งนี้"
            (r"\b(tomorrow|พรุ่งนี้)\b", timedelta(days=1)),
            # "next week" or "สัปดาห์หน้า"
            (r"\b(next week|สัปดาห์หน้า)\b", timedelta(weeks=1)),
            # "in X days"
            (r"\bin\s+(\d+)\s+days?\b", None),  # Special handling
        ]

        # Date format patterns
        date_patterns = [
            (r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", "%d/%m/%Y"),  # DD/MM/YYYY
            (r"\b(\d{4})-(\d{2})-(\d{2})\b", "%Y-%m-%d"),  # YYYY-MM-DD
        ]

        weekday_pattern = re.compile(
            r"\b(on\s+)?(mon(day)?|tue(s(day)?)?|wed(nesday)?|thu(r(sday)?)?|fri(day)?|sat(urday)?|sun(day)?)",
            re.IGNORECASE,
        )

        # Month names for better detection
        month_pattern = re.compile(
            r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|"
            r"jul(y)?|aug(ust)?|sep(t(ember)?)?|oct(ober)?|nov(ember)?|dec(ember)?)\s+\d{1,2}\b",
            re.IGNORECASE,
        )

        for msg in messages:
            msg_lower = msg.lower()

            # Skip non-event-ish messages to reduce false positives.
            if (
                not any(k in msg_lower for k in event_keywords)
                and not weekday_pattern.search(msg_lower)
                and not month_pattern.search(msg_lower)
            ):
                # Still allow strict date formats (e.g., 2025-01-15) even without keywords.
                if not any(re.search(pat, msg) for pat, _fmt in date_patterns):
                    continue

            # If dateparser is available, try a best-effort parse using RELATIVE_BASE.
            # We only accept results that are today or in the future.
            if dateparser_parse:
                try:
                    dt = dateparser_parse(
                        msg,
                        settings={
                            "RELATIVE_BASE": datetime.now(BANGKOK_TZ),
                            "PREFER_DATES_FROM": "future",
                        },
                    )
                    if dt and dt.date() >= today:
                        title = self._extract_title_from_context(msg, dt.strftime("%Y-%m-%d"))
                        events.append(
                            ExtractedEvent(
                                event_date=dt.date(),
                                title=title,
                                description="",
                                source_text=msg[:100],
                                confidence="low",
                            )
                        )
                        # Keep going to allow multiple events per message if explicit dates exist.
                except Exception:
                    pass

            # Check relative date patterns
            for pattern, delta in patterns:
                match = re.search(pattern, msg_lower)
                if match:
                    if delta is None:
                        # Handle "in X days"
                        days = int(match.group(1))
                        event_date = today + timedelta(days=days)
                    else:
                        event_date = today + delta

                    # Try to extract title from surrounding text
                    title = self._extract_title_from_context(msg, match.group(0))

                    events.append(
                        ExtractedEvent(
                            event_date=event_date,
                            title=title,
                            description="",
                            source_text=msg[:100],
                            confidence="low",
                        )
                    )

            # Check absolute date patterns
            for pattern, fmt in date_patterns:
                for match in re.finditer(pattern, msg):
                    try:
                        date_str = match.group(0)
                        event_date = datetime.strptime(date_str, fmt).date()

                        if event_date >= today:
                            title = self._extract_title_from_context(msg, date_str)
                            events.append(
                                ExtractedEvent(
                                    event_date=event_date,
                                    title=title,
                                    description="",
                                    source_text=msg[:100],
                                    confidence="low",
                                )
                            )
                    except ValueError:
                        continue

        logger.info(f"📅 Fallback extraction found {len(events)} events")
        return events

    def _extract_title_from_context(self, message: str, date_match: str) -> str:
        """
        Try to extract a meaningful title from the message context.
        Enhanced to handle patterns like "Dear all, meeting on Friday".

        Args:
            message: Full message text
            date_match: The matched date string

        Returns:
            Extracted title or generic "Event"
        """
        # Remove the date portion first
        cleaned = message.replace(date_match, "").strip()

        # Remove greetings and announcement patterns
        greeting_patterns = [
            r"^dear\s+all[,:]?\s*",
            r"^hi\s+everyone[,:]?\s*",
            r"^hi\s+team[,:]?\s*",
            r"^hello\s+all[,:]?\s*",
            r"^hey\s+everyone[,:]?\s*",
            r"^everyone[,:]?\s*",
        ]

        for pattern in greeting_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

        # Look for event keywords and extract context around them
        event_patterns = [
            (r"([\w\s]+?)\s+(?:on|at|this|next|tomorrow|today)", r"\1"),  # "meeting on Friday" -> "meeting"
            (r"(?:have|having)\s+(?:a\s+)?([\w\s]+)", r"\1"),  # "having a workshop" -> "workshop"
            (r"(?:let's|let\s+us)\s+([\w\s]+)", r"\1"),  # "let's review" -> "review"
        ]

        for search_pattern, _extract_pattern in event_patterns:
            match = re.search(search_pattern, cleaned, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                # Clean up extracted title
                title = re.sub(r"\b(is|are|the|a|an|for|to)\b", "", title, flags=re.IGNORECASE)
                title = " ".join(title.split())  # Normalize whitespace
                if len(title) > 3:
                    return title[:50]

        # Fallback: Remove common filler words and take what's left
        cleaned = re.sub(r"\b(is|are|the|a|an|on|at|for|to|we|have|has|there|this)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.split())  # Normalize whitespace

        if len(cleaned) > 5:
            return cleaned[:50]

        return "Event"

    def _deduplicate_events(
        self,
        events: list[ExtractedEvent],
    ) -> list[ExtractedEvent]:
        """
        Remove duplicate events (same date and similar title).

        Args:
            events: List of extracted events

        Returns:
            Deduplicated list
        """
        seen = set()
        unique = []

        for event in events:
            # Create a key from date and normalized title
            key = (
                event.event_date.isoformat(),
                event.title.lower().strip()[:30],
            )

            if key not in seen:
                seen.add(key)
                unique.append(event)

        return unique

    def get_extraction_count(self) -> int:
        """Get total number of extraction operations performed."""
        return self._extraction_count


# Singleton instance
date_extraction_service = DateExtractionService()
