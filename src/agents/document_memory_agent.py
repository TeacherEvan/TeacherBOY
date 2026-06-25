"""Document Memory Agent - Stores PDF/DOCX files for later use."""

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import FileMessageContent, MessageEvent, TextMessageContent

from src.config import settings
from src.services.bot_identity_service import get_bot_identity_service

from .base_agent import BaseAgent

if TYPE_CHECKING:
    from src.services.document_memory_service import DocumentMemoryService

logger = logging.getLogger(__name__)


class DocumentMemoryAgent(BaseAgent):
    """Agent that stores and retrieves PDF/DOCX files for each chat."""

    def __init__(self, document_service: "DocumentMemoryService"):
        super().__init__(
            name="DocumentMemoryAgent",
            description="Stores PDF/DOCX files for later retrieval",
        )
        self._document_service = document_service

    def get_priority(self) -> int:
        return 8

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        if not settings.document_memory_enabled:
            return False

        if isinstance(event.message, FileMessageContent):
            return True

        if isinstance(event.message, TextMessageContent):
            prefix, rest = get_bot_identity_service().split_command_prefix(text)
            if prefix is None:
                return False

            rest_clean = rest.strip()
            rest_lower = rest_clean.lower()

            # Direct doc commands
            if (
                rest_lower.startswith("doc") or
                rest_lower.startswith("analyze doc ") or
                rest_lower.startswith("summarize doc ") or
                rest_lower.startswith("doc analyze ") or
                rest_lower.startswith("doc summarize ")
            ):
                return True

            # Direct analyze/summarize followed by document ID/Name check
            if rest_lower.startswith("analyze ") or rest_lower.startswith("summarize "):
                parts = rest_clean.split(None, 1)
                if len(parts) > 1:
                    target = parts[1].strip()
                    chat_id = self._get_chat_id(event)
                    # Check if target is a valid doc ID (hex 32 chars)
                    if re.match(r"^[a-f0-9]{32}$", target.lower()):
                        doc_meta = await self._document_service.get_document(chat_id, target)
                        if doc_meta:
                            return True
                    # Check if target matches doc file name fuzzy
                    matches = self._document_service.find_by_name(chat_id, target)
                    if matches:
                        return True

        return False

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        if isinstance(event.message, FileMessageContent):
            return await self._handle_file(event, line_bot_api)

        if isinstance(event.message, TextMessageContent):
            return await self._handle_command(event, text, line_bot_api)

        return False

    async def _handle_file(self, event: MessageEvent, line_bot_api: MessagingApi) -> bool:
        message_id = getattr(event.message, "id", None)
        file_name = getattr(event.message, "file_name", None)
        file_size = getattr(event.message, "file_size", None)

        if not isinstance(message_id, str) or not message_id.strip():
            await self._send_reply(event, line_bot_api, "❌ Missing file message ID.")
            return False

        if not isinstance(file_name, str) or not file_name.strip():
            await self._send_reply(event, line_bot_api, "❌ Missing file name.")
            return False

        if isinstance(file_size, int) and file_size > self._document_service.max_file_size_bytes:
            await self._send_reply(
                event,
                line_bot_api,
                (f"⚠️ File too large for document memory.\nMax size: {settings.document_max_file_size_mb:.1f} MB"),
            )
            return True

        chat_id = self._get_chat_id(event)
        user_id = self._get_user_id(event)

        logger.info(f"📄 Downloading document {message_id} ({file_name}) from LINE...")
        file_bytes = await self._download_file(message_id)

        if not file_bytes:
            await self._send_reply(event, line_bot_api, "❌ Failed to download file.")
            return False

        try:
            metadata = await self._document_service.add_document(
                chat_id=chat_id,
                file_name=file_name,
                file_bytes=file_bytes,
                user_id=user_id,
            )
        except ValueError as e:
            if str(e) == "file_too_large":
                await self._send_reply(
                    event,
                    line_bot_api,
                    (f"⚠️ File too large for document memory.\nMax size: {settings.document_max_file_size_mb:.1f} MB"),
                )
                return True
            if str(e) == "unsupported_type":
                await self._send_reply(
                    event,
                    line_bot_api,
                    "⚠️ Unsupported file type. Please upload PDF, DOCX, or Excel only.",
                )
                return True
            await self._send_reply(event, line_bot_api, "❌ Failed to store document.")
            return False

        text_chars = metadata.get("text_chars", 0)
        doc_id = metadata.get("id")
        reply = (
            f"✅ Stored document: {metadata.get('file_name')}\n"
            f"ID: {doc_id}\n"
            f"Extracted text: {text_chars} chars\n\n"
            f"Use: '{get_bot_identity_service().get_profile().display_name} docs' to list, "
            f"'{get_bot_identity_service().get_profile().display_name} doc <ID>' to view."
        )
        if settings.is_document_memory_configured():
            reply += "\n\n📦 HF Hub persistence enabled (safe across restarts)."
        else:
            reply += "\n\n📦 Stored locally. Set DOCUMENT_HF_REPO_ID for cloud backup."

        await self._send_reply(event, line_bot_api, reply)
        return True

    async def _handle_command(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        chat_id = self._get_chat_id(event)
        display_name = get_bot_identity_service().get_profile().display_name
        prefix, rest = get_bot_identity_service().split_command_prefix(text)

        if not prefix:
            return False

        rest = rest.strip()
        rest_lower = rest.lower()

        # Check for analyze/summarize commands
        target_doc = None
        is_analyze = False

        if rest_lower.startswith("analyze doc "):
            target_doc = rest[len("analyze doc "):].strip()
            is_analyze = True
        elif rest_lower.startswith("summarize doc "):
            target_doc = rest[len("summarize doc "):].strip()
            is_analyze = True
        elif rest_lower.startswith("doc analyze "):
            target_doc = rest[len("doc analyze "):].strip()
            is_analyze = True
        elif rest_lower.startswith("doc summarize "):
            target_doc = rest[len("doc summarize "):].strip()
            is_analyze = True
        elif rest_lower.startswith("analyze "):
            target_doc = rest[len("analyze "):].strip()
            is_analyze = True
        elif rest_lower.startswith("summarize "):
            target_doc = rest[len("summarize "):].strip()
            is_analyze = True

        if is_analyze and target_doc:
            text_content = self._document_service.get_document_text(chat_id, target_doc)
            doc_name = target_doc

            if text_content is None:
                # Fuzzy match by name
                matches = self._document_service.find_by_name(chat_id, target_doc)
                if matches:
                    first_match = matches[0]
                    doc_id = first_match.get("id")
                    doc_name = first_match.get("file_name", target_doc)
                    text_content = self._document_service.get_document_text(chat_id, doc_id)

            if text_content is None:
                await self._send_reply(event, line_bot_api, f"❌ Document not found: {target_doc}")
                return True

            # Send initial confirmation
            await self._send_reply(event, line_bot_api, f"⏳ Summarizing and analyzing '{doc_name}'...")

            # Call LLM fallback chain
            from src.utils.llm_fallback import chat_completion_with_fallback

            prompt = (
                f"You are Ms. Green. Please analyze and summarize the following document content.\n"
                f"Document Name: {doc_name}\n\n"
                f"--- Start Content ---\n"
                f"{text_content}\n"
                f"--- End Content ---\n\n"
                f"Under the following constraints, formulate a helpful and structured response for the user:\n"
                f"1. Summarize the main topics, key themes, and important details of the document.\n"
                f"2. Keep the summary professional, clear, and easy to read."
            )

            messages = [
                {
                    "role": "system",
                    "content": "You are Ms. Green. You analyze and summarize document contents clearly and concisely for the user."
                },
                {"role": "user", "content": prompt}
            ]

            summary = await chat_completion_with_fallback(messages, temperature=0.7)
            if not summary:
                summary = "❌ Failed to generate document analysis. Please try again."

            # Push the final result
            source = getattr(event, "source", None)
            target = getattr(source, "group_id", None) or getattr(source, "room_id", None) or getattr(source, "user_id", None)
            if target:
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=target,
                        messages=[TextMessage(text=summary)],
                        notificationDisabled=False,
                    )
                )
            return True

        if rest_lower in ("docs", "docs list", "doc list"):
            docs = self._document_service.list_documents(chat_id)
            if not docs:
                await self._send_reply(event, line_bot_api, "📄 No documents stored yet.")
                return True

            lines = ["📄 Stored documents:"]
            for doc in docs[:10]:
                lines.append(f"• {doc.get('file_name')} (ID: {doc.get('id')})")
            if len(docs) > 10:
                lines.append(f"...and {len(docs) - 10} more")
            await self._send_reply(event, line_bot_api, "\n".join(lines))
            return True

        if rest_lower.startswith("doc search "):
            query = rest[len("doc search ") :].strip()
            if not query:
                await self._send_reply(event, line_bot_api, "⚠️ Provide a search query.")
                return True

            results = self._document_service.search_documents(chat_id, query)
            if not results:
                await self._send_reply(event, line_bot_api, "🔎 No matches found.")
                return True

            lines = [f"🔎 Matches for '{query}':"]
            for result in results:
                lines.append(f"• {result.get('file_name')} (ID: {result.get('id')})\n  {result.get('snippet')}")
            await self._send_reply(event, line_bot_api, "\n".join(lines))
            return True

        if rest_lower in ("doc clear", "docs clear"):
            cleared = self._document_service.clear_documents(chat_id)
            if cleared:
                await self._send_reply(event, line_bot_api, "🧹 Document memory cleared for this chat.")
            else:
                await self._send_reply(event, line_bot_api, "📄 No documents to clear.")
            return True

        if rest_lower.startswith("doc delete "):
            doc_id = rest[len("doc delete ") :].strip()
            if not doc_id:
                await self._send_reply(event, line_bot_api, "⚠️ Provide a document ID.")
                return True
            deleted = self._document_service.delete_document(chat_id, doc_id)
            if deleted:
                await self._send_reply(event, line_bot_api, "🗑️ Document deleted.")
            else:
                await self._send_reply(event, line_bot_api, "❌ Document not found.")
            return True

        if rest_lower.startswith("doc "):
            doc_id = rest[len("doc ") :].strip()
            if not doc_id:
                await self._send_reply(event, line_bot_api, "⚠️ Provide a document ID.")
                return True

            text_content = self._document_service.get_document_text(chat_id, doc_id)
            if text_content is None:
                matches = self._document_service.find_by_name(chat_id, doc_id)
                if matches:
                    suggestions = ", ".join(m.get("id", "") for m in matches[:3])
                    await self._send_reply(
                        event,
                        line_bot_api,
                        f"❌ Document ID not found. Matching IDs: {suggestions}",
                    )
                else:
                    await self._send_reply(event, line_bot_api, "❌ Document not found.")
                return True

            preview = text_content[:1200]
            if len(text_content) > 1200:
                preview += "\n... (truncated)"
            await self._send_reply(event, line_bot_api, preview)
            return True

        await self._send_reply(
            event,
            line_bot_api,
            "📄 Document commands:\n"
            f"• {display_name} docs\n"
            f"• {display_name} doc <ID>\n"
            f"• {display_name} doc search <query>\n"
            f"• {display_name} doc delete <ID>\n"
            f"• {display_name} doc clear",
        )
        return True

    async def _download_file(self, message_id: str) -> bytes | None:
        try:
            configuration = Configuration(access_token=settings.line_channel_access_token)

            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)

                response = await asyncio.to_thread(
                    blob_api.get_message_content,
                    message_id,
                )

                if response is None:
                    logger.warning("❌ Response is None from LINE API")
                    return None

                if isinstance(response, bytes):
                    return response
                if isinstance(response, bytearray):
                    return bytes(response)
                if hasattr(response, "read") and callable(getattr(response, "read", None)):
                    return response.read()

                chunks: list[bytes] = []
                try:
                    for chunk in response:  # type: ignore[union-attr]
                        if isinstance(chunk, bytes):
                            chunks.append(chunk)
                    return b"".join(chunks)
                except Exception:
                    return None

        except Exception as e:
            logger.error(f"❌ Failed to download file {message_id}: {e}", exc_info=True)
            return None

    def _get_chat_id(self, event: MessageEvent) -> str:
        source = getattr(event, "source", None)
        group_id = getattr(source, "group_id", None) if source else None
        room_id = getattr(source, "room_id", None) if source else None
        user_id = getattr(source, "user_id", None) if source else None

        if group_id:
            return f"group_{group_id}"
        if room_id:
            return f"room_{room_id}"
        return f"user_{user_id or 'unknown'}"

    def _get_user_id(self, event: MessageEvent) -> str | None:
        source = getattr(event, "source", None)
        return getattr(source, "user_id", None) if source else None

    async def _send_reply(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        text: str,
    ) -> None:
        reply_token = getattr(event, "reply_token", None)
        if not reply_token:
            return

        await asyncio.to_thread(
            line_bot_api.reply_message,
            ReplyMessageRequest(
                replyToken=reply_token,
                messages=[TextMessage(text=text, quickReply=None, quoteToken=None)],
                notificationDisabled=False,
            ),
        )
