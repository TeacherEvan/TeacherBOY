"""Structured record writes for Convex-backed persistence."""

from dataclasses import dataclass
from typing import Optional

from src.services.convex_client import ConvexClient


@dataclass
class StructuredRecordsService:
    """Writes user and interaction records to the Convex HTTP layer."""

    convex_client: ConvexClient

    async def upsert_user(
        self,
        line_user_id: str,
        display_name: Optional[str] = None,
        role: Optional[str] = None,
    ) -> dict:
        payload = {
            "lineUserId": line_user_id,
            "displayName": display_name,
            "role": role,
        }
        return await self.convex_client.post("/records/upsertUser", payload)

    async def record_interaction(
        self,
        line_user_id: str,
        source_chat_id: str,
        message_type: str,
        direction: str,
        text_preview: Optional[str] = None,
        handled_agent: Optional[str] = None,
    ) -> dict:
        payload = {
            "lineUserId": line_user_id,
            "sourceChatId": source_chat_id,
            "messageType": message_type,
            "direction": direction,
            "textPreview": text_preview,
            "handledAgent": handled_agent,
        }
        return await self.convex_client.post("/records/appendInteraction", payload)