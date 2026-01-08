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

import logging
import json
import re
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

# Extraction prompt template
EXTRACTION_PROMPT = """You are an AI assistant that extracts calendar events from chat messages.

Analyze the following messages and identify any dates, events, appointments, deadlines, or scheduled activities mentioned.

MESSAGES TO ANALYZE:
{messages}

TODAY'S DATE: {today}
CURRENT YEAR: {year}

INSTRUCTIONS:
1. Look for explicit dates (e.g., "January 15", "15/01/2025", "next Friday")
2. Look for relative dates (e.g., "tomorrow", "next week", "in 3 days")
3. Identify what the event/activity is for each date
4. Extract a short title and optional description
5. Only extract dates that are clearly mentioned - don't invent events
6. Ignore past dates (before today)
7. Parse Thai dates and Thai language events if present
8. ALWAYS use the actual year number (e.g., {year}), NEVER use "YYYY" as a placeholder
9. If the year is not specified, use {year} for future dates or {next_year} for dates that have passed this year

OUTPUT FORMAT (JSON array):
[
  {{
    "date": "{year}-01-15",
    "title": "Short event title (max 50 chars)",
    "description": "Optional longer description",
    "source_text": "Original message text this was extracted from",
    "confidence": "high" | "medium" | "low"
  }}
]

If no dates/events are found, return an empty array: []

RESPOND ONLY WITH THE JSON ARRAY, NO OTHER TEXT."""


@dataclass
class ExtractedEvent:
    """Represents a single extracted event."""
    
    event_date: date
    title: str
    description: str
    source_text: str
    confidence: str  # high, medium, low
    
    def to_dict(self) -> Dict[str, Any]:
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
        messages: List[str],
        max_events: int = 10,
    ) -> List[ExtractedEvent]:
        """
        Extract calendar events from a list of message texts.
        
        Args:
            messages: List of message text strings to analyze
            max_events: Maximum number of events to extract
            
        Returns:
            List of ExtractedEvent objects
        """
        if not messages:
            logger.debug("📅 No messages to extract from")
            return []
        
        # Format messages for prompt
        numbered_messages = "\n".join(
            f"{i+1}. {msg}" for i, msg in enumerate(messages)
        )
        
        today = datetime.now(BANGKOK_TZ).date()
        current_year = today.year
        prompt = EXTRACTION_PROMPT.format(
            messages=numbered_messages,
            today=today.isoformat(),
            year=current_year,
            next_year=current_year + 1,
        )
        
        try:
            # Use GitHub Models Service for extraction
            from src.services.github_models_service import github_models_service
            
            if not github_models_service.is_configured():
                logger.warning("📅 GitHub Models not configured, using fallback extraction")
                return self._fallback_extraction(messages, today)
            
            response = await github_models_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model="openai/gpt-4o-mini",  # Use mini for cost efficiency
                temperature=0.1,  # Low temperature for consistent extraction
                max_tokens=2000,
            )
            
            if not response:
                logger.warning("📅 No response from AI, using fallback extraction")
                return self._fallback_extraction(messages, today)
            
            # Parse JSON response
            events = self._parse_extraction_response(response, today)
            
            # Deduplicate and limit
            events = self._deduplicate_events(events)[:max_events]
            
            self._extraction_count += 1
            logger.info(f"📅 Extracted {len(events)} events from {len(messages)} messages")
            
            return events
            
        except Exception as e:
            logger.error(f"📅 AI extraction failed: {e}", exc_info=True)
            return self._fallback_extraction(messages, today)
    
    def _parse_extraction_response(
        self,
        response: str,
        today: date,
    ) -> List[ExtractedEvent]:
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
            # Clean response (remove markdown code blocks if present)
            cleaned = response.strip()
            if cleaned.startswith("```"):
                # Remove ```json and ``` markers
                cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)
            
            data = json.loads(cleaned)
            
            if not isinstance(data, list):
                logger.warning("📅 AI response is not a list")
                return []
            
            for item in data:
                try:
                    # Parse date
                    date_str = item.get("date", "")
                    try:
                        event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    except ValueError:
                        logger.debug(f"📅 Could not parse date: {date_str}")
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
        messages: List[str],
        today: date,
    ) -> List[ExtractedEvent]:
        """
        Simple regex-based fallback extraction when AI is unavailable.
        
        Args:
            messages: List of message texts
            today: Today's date
            
        Returns:
            List of ExtractedEvent objects
        """
        events = []
        
        # Simple patterns to match
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
        
        for msg in messages:
            msg_lower = msg.lower()
            
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
                    
                    events.append(ExtractedEvent(
                        event_date=event_date,
                        title=title,
                        description="",
                        source_text=msg[:100],
                        confidence="low",
                    ))
            
            # Check absolute date patterns
            for pattern, fmt in date_patterns:
                for match in re.finditer(pattern, msg):
                    try:
                        date_str = match.group(0)
                        event_date = datetime.strptime(date_str, fmt).date()
                        
                        if event_date >= today:
                            title = self._extract_title_from_context(msg, date_str)
                            events.append(ExtractedEvent(
                                event_date=event_date,
                                title=title,
                                description="",
                                source_text=msg[:100],
                                confidence="low",
                            ))
                    except ValueError:
                        continue
        
        logger.info(f"📅 Fallback extraction found {len(events)} events")
        return events
    
    def _extract_title_from_context(self, message: str, date_match: str) -> str:
        """
        Try to extract a meaningful title from the message context.
        
        Args:
            message: Full message text
            date_match: The matched date string
            
        Returns:
            Extracted title or generic "Event"
        """
        # Remove the date portion
        cleaned = message.replace(date_match, "").strip()
        
        # Remove common filler words
        cleaned = re.sub(r"\b(is|are|the|a|an|on|at|for|to)\b", "", cleaned, flags=re.I)
        cleaned = " ".join(cleaned.split())  # Normalize whitespace
        
        if len(cleaned) > 5:
            return cleaned[:50]
        
        return "Event"
    
    def _deduplicate_events(
        self,
        events: List[ExtractedEvent],
    ) -> List[ExtractedEvent]:
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
