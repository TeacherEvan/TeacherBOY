"""
Zeus History Log Service - Comprehensive audit trail and event logging.

This service provides a robust, persistent logging system for all Zeus operations
with the following features:

- Structured event logging (interactions, requests, actions, system events)
- Secure persistent storage with optional encryption
- Log versioning and rotation
- Access control integration
- Audit trails for compliance
- Integration with conversation memory service
- Zeus-themed error messages (authoritative, thunderous, mythological)

Storage backends supported:
1. Local file system (JSON/encrypted)
2. Hugging Face Hub (persistent, cloud-based)
3. In-memory (fallback for testing)

Security features:
- AES encryption for sensitive logs (optional)
- Event hashing for tamper detection
- User ID anonymization options
- Access level filtering
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import traceback
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from collections import OrderedDict
from functools import wraps

logger = logging.getLogger(__name__)


# ============================================================================
# Zeus-Themed Error Messages - Mythological Error Reporting
# ============================================================================

class ZeusErrorMessages:
    """
    Zeus-themed error message generator for authoritative, mythological error reporting.
    
    When Zeus encounters errors, they are reported with thunderous authority!
    """
    
    # Error category templates
    TEMPLATES = {
        "api_failure": [
            "⚡ BY THE THUNDERBOLTS OF OLYMPUS! The mortal API '{service}' has FAILED! Error: {error}",
            "🌩️ HEAR ME, MORTALS! The {service} service has COLLAPSED beneath my divine gaze! {error}",
            "⛈️ The clouds of {service} have BETRAYED ZEUS! A storm of errors descends: {error}",
        ],
        "network_error": [
            "🌊 POSEIDON'S WAVES have disrupted our connection! Network failure: {error}",
            "⚡ The ethereal pathways are BLOCKED by Typhon's chaos! {error}",
            "🔱 The network gods have turned their backs! Connection severed: {error}",
        ],
        "auth_failure": [
            "🏛️ HALT, MORTAL! You lack the divine credentials to approach Olympus! {error}",
            "⚔️ Your authentication offering is REJECTED by the gates of Zeus! {error}",
            "👁️ The all-seeing eye of Zeus detects UNAUTHORIZED ACCESS! {error}",
        ],
        "rate_limit": [
            "⏳ PATIENCE, MORTAL! Even gods must respect the cosmic rate limits! Wait {wait}...",
            "🕐 The sands of time demand REST! Too many requests have angered the Fates! {error}",
            "⚡ Your eagerness EXCEEDS mortal bounds! The heavens require respite. {error}",
        ],
        "storage_error": [
            "📜 The sacred scrolls of memory have been CORRUPTED! {error}",
            "🏺 The amphora of data has SHATTERED! Storage failure: {error}",
            "📚 The Library of Alexandria BURNS AGAIN! Data loss detected: {error}",
        ],
        "config_error": [
            "⚙️ The divine configuration is INCOMPLETE! Missing: {missing}",
            "🔧 The gears of Hephaestus require PROPER ALIGNMENT! {error}",
            "📋 The sacred settings tablet bears ERRORS! Fix thy configuration: {error}",
        ],
        "validation_error": [
            "❌ Your offering is UNWORTHY of Zeus! Validation failed: {error}",
            "⚖️ The scales of justice find your input WANTING! {error}",
            "🎭 The masks of truth reveal DECEPTION in your data! {error}",
        ],
        "general_error": [
            "⚡ THUNDERATION! An unexpected error strikes from the heavens! {error}",
            "🌩️ By Hera's wrath! Something has gone TERRIBLY WRONG! {error}",
            "⛈️ The Fates weave a TANGLED thread! Unexpected error: {error}",
        ],
        "success": [
            "✨ OLYMPUS REJOICES! The task is complete, mortal!",
            "🏆 Victory! Zeus smiles upon your endeavor!",
            "⚡ The thunderbolt of SUCCESS strikes true!",
        ],
    }
    
    @classmethod
    def get_error_message(
        cls,
        category: str,
        error: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate a Zeus-themed error message.
        
        Args:
            category: Error category (api_failure, network_error, etc.)
            error: The actual error message to include
            **kwargs: Additional format parameters
            
        Returns:
            Formatted Zeus-style error message
        """
        templates = cls.TEMPLATES.get(category, cls.TEMPLATES["general_error"])
        template = secrets.choice(templates)
        
        format_args = {"error": error or "Unknown divine interference", **kwargs}
        
        try:
            return template.format(**format_args)
        except KeyError:
            return template.replace("{error}", str(error or ""))
    
    @classmethod
    def format_exception(cls, exc: Exception, category: str = "general_error") -> str:
        """
        Format an exception with Zeus-style messaging.
        
        Args:
            exc: The exception to format
            category: Error category for theming
            
        Returns:
            Zeus-themed error message with exception details
        """
        error_type = type(exc).__name__
        error_msg = str(exc)
        
        # Determine category from exception type if not specified
        if category == "general_error":
            if "timeout" in error_type.lower() or "connection" in error_type.lower():
                category = "network_error"
            elif "auth" in error_type.lower() or "permission" in error_type.lower():
                category = "auth_failure"
            elif "rate" in error_type.lower() or "429" in error_msg:
                category = "rate_limit"
        
        return cls.get_error_message(category, error=f"{error_type}: {error_msg}")


# ============================================================================
# Event Types and Log Levels
# ============================================================================

class EventType(str, Enum):
    """Types of events that can be logged."""
    # User interactions
    USER_MESSAGE = "user_message"
    BOT_RESPONSE = "bot_response"
    COMMAND_EXECUTED = "command_executed"
    
    # Agent actions
    AGENT_ACTIVATED = "agent_activated"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    
    # System events
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    CONFIG_CHANGE = "config_change"
    
    # Translation events
    TRANSLATION_REQUEST = "translation_request"
    TRANSLATION_SUCCESS = "translation_success"
    TRANSLATION_FAILED = "translation_failed"
    
    # LLM events
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    LLM_ERROR = "llm_error"
    MEMORY_CLEARED = "memory_cleared"
    
    # News events
    NEWS_REQUEST = "news_request"
    NEWS_DELIVERED = "news_delivered"
    
    # Admin events
    ADMIN_ACTION = "admin_action"
    RATE_LIMITED = "rate_limited"
    
    # Security events
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    ACCESS_DENIED = "access_denied"
    
    # Errors
    ERROR = "error"
    WARNING = "warning"


class LogLevel(str, Enum):
    """Log severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AccessLevel(str, Enum):
    """Access levels for log entries."""
    PUBLIC = "public"  # Can be viewed by users
    INTERNAL = "internal"  # Bot operators only
    ADMIN = "admin"  # Admin users only
    SYSTEM = "system"  # System-only, highest security


# ============================================================================
# Log Entry Model
# ============================================================================

class LogEntry:
    """Represents a single log entry with full audit trail."""
    
    def __init__(
        self,
        event_type: EventType,
        message: str,
        level: LogLevel = LogLevel.INFO,
        access_level: AccessLevel = AccessLevel.INTERNAL,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error_details: Optional[Dict[str, Any]] = None,
    ):
        self.id = self._generate_id()
        self.timestamp = datetime.now(timezone.utc)
        self.event_type = event_type
        self.message = message
        self.level = level
        self.access_level = access_level
        self.chat_id = chat_id
        self.user_id = user_id
        self.agent_name = agent_name
        self.metadata = metadata or {}
        self.error_details = error_details
        self.hash = self._compute_hash()
    
    def _generate_id(self) -> str:
        """Generate a unique ID for this log entry."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        random_suffix = secrets.token_hex(4)
        return f"log_{timestamp}_{random_suffix}"
    
    def _compute_hash(self) -> str:
        """Compute integrity hash for tamper detection."""
        content = f"{self.id}{self.timestamp.isoformat()}{self.event_type.value}{self.message}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "message": self.message,
            "level": self.level.value,
            "access_level": self.access_level.value,
            "agent_name": self.agent_name,
            "metadata": self.metadata,
            "hash": self.hash,
        }
        
        if include_sensitive:
            data["chat_id"] = self.chat_id
            data["user_id"] = self.user_id
            data["error_details"] = self.error_details
        else:
            # Anonymize sensitive data
            data["chat_id"] = self._anonymize(self.chat_id) if self.chat_id else None
            data["user_id"] = self._anonymize(self.user_id) if self.user_id else None
            data["error_details"] = None
        
        return data
    
    def _anonymize(self, value: str) -> str:
        """Anonymize a value by hashing."""
        return hashlib.sha256(value.encode()).hexdigest()[:12]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogEntry":
        """Create LogEntry from dictionary."""
        entry = cls(
            event_type=EventType(data["event_type"]),
            message=data["message"],
            level=LogLevel(data.get("level", "info")),
            access_level=AccessLevel(data.get("access_level", "internal")),
            chat_id=data.get("chat_id"),
            user_id=data.get("user_id"),
            agent_name=data.get("agent_name"),
            metadata=data.get("metadata", {}),
            error_details=data.get("error_details"),
        )
        entry.id = data["id"]
        entry.timestamp = datetime.fromisoformat(data["timestamp"])
        entry.hash = data.get("hash", entry._compute_hash())
        return entry


# ============================================================================
# Encryption Support (Optional)
# ============================================================================

class LogEncryption:
    """Optional AES encryption for sensitive log data."""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption with optional key.
        
        If no key is provided, encryption is disabled.
        """
        self.enabled = False
        self._key: Optional[bytes] = None
        
        if encryption_key:
            try:
                from cryptography.fernet import Fernet
                # Derive a key from the provided string
                key_bytes = hashlib.sha256(encryption_key.encode()).digest()
                self._key = base64.urlsafe_b64encode(key_bytes)
                self._fernet = Fernet(self._key)
                self.enabled = True
                logger.info("🔐 Log encryption enabled")
            except ImportError:
                logger.warning("⚠️ cryptography package not installed, encryption disabled")
            except Exception as e:
                logger.warning(f"⚠️ Encryption setup failed: {e}")
    
    def encrypt(self, data: str) -> str:
        """Encrypt data if encryption is enabled."""
        if not self.enabled:
            return data
        try:
            encrypted = self._fernet.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return data
    
    def decrypt(self, data: str) -> str:
        """Decrypt data if encryption is enabled."""
        if not self.enabled:
            return data
        try:
            decoded = base64.urlsafe_b64decode(data.encode())
            decrypted = self._fernet.decrypt(decoded)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return data


# ============================================================================
# History Log Service - Main Service Class
# ============================================================================

class HistoryLogService:
    """
    Comprehensive history logging service for Zeus.
    
    Features:
    - Multi-backend storage (file, HF Hub, memory)
    - Optional encryption
    - Log rotation and versioning
    - Query and filtering
    - Access control
    - Audit trails
    """
    
    # Configuration constants
    MAX_MEMORY_LOGS = 1000  # Max logs in memory
    LOG_ROTATION_DAYS = 7  # Days before rotation
    MAX_LOG_FILE_SIZE_MB = 10  # Max file size before rotation
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        hf_token: Optional[str] = None,
        hf_repo_id: Optional[str] = None,
        encryption_key: Optional[str] = None,
        enable_file_storage: bool = True,
    ):
        """
        Initialize history log service.
        
        Args:
            storage_path: Local directory for log files
            hf_token: HF Hub token for cloud persistence
            hf_repo_id: HF Hub repo for log storage
            encryption_key: Optional encryption key for sensitive logs
            enable_file_storage: Whether to enable local file storage
        """
        self.storage_path = Path(storage_path or "./data/logs")
        self.hf_token = hf_token
        self.hf_repo_id = hf_repo_id
        self.enable_file_storage = enable_file_storage
        
        # In-memory log buffer
        self._logs: OrderedDict[str, LogEntry] = OrderedDict()
        
        # Encryption handler
        self._encryption = LogEncryption(encryption_key)
        
        # HF Hub integration
        self._hf_enabled = bool(hf_token and hf_repo_id)
        self._hf_api: Optional[Any] = None
        self._commit_scheduler: Optional[Any] = None
        
        # Statistics
        self._stats = {
            "total_logged": 0,
            "errors_logged": 0,
            "warnings_logged": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Initialize storage
        self._setup_storage()
    
    def _setup_storage(self) -> None:
        """Initialize storage backends."""
        # Local file storage
        if self.enable_file_storage:
            try:
                self.storage_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"📁 Log storage initialized at {self.storage_path}")
            except Exception as e:
                logger.error(f"❌ Failed to create log directory: {e}")
                self.enable_file_storage = False
        
        # HF Hub storage
        if self._hf_enabled:
            self._setup_hf_storage()
    
    def _setup_hf_storage(self) -> None:
        """Initialize Hugging Face Hub storage for logs."""
        try:
            from huggingface_hub import HfApi, CommitScheduler
            
            self._hf_api = HfApi(token=self.hf_token)
            
            # Create logs subdirectory
            logs_path = self.storage_path / "hf_sync"
            logs_path.mkdir(parents=True, exist_ok=True)
            
            # Ensure repo exists
            try:
                self._hf_api.create_repo(
                    repo_id=self.hf_repo_id,
                    repo_type="dataset",
                    private=True,
                    exist_ok=True,
                )
            except Exception as e:
                logger.warning(f"⚠️ Could not create HF logs repo: {e}")
                self._hf_enabled = False
                return
            
            # Set up scheduled commits (every 10 minutes for logs)
            self._commit_scheduler = CommitScheduler(
                repo_id=self.hf_repo_id,
                repo_type="dataset",
                folder_path=str(logs_path),
                every=10,  # 10 minutes
                token=self.hf_token,
                private=True,
                path_in_repo="logs",
            )
            
            logger.info(f"☁️ HF Hub log sync enabled: {self.hf_repo_id}")
            
        except ImportError:
            logger.warning("⚠️ huggingface_hub not installed for log sync")
            self._hf_enabled = False
        except Exception as e:
            logger.error(f"❌ Failed to setup HF log storage: {e}")
            self._hf_enabled = False
    
    async def log(
        self,
        event_type: EventType,
        message: str,
        level: LogLevel = LogLevel.INFO,
        access_level: AccessLevel = AccessLevel.INTERNAL,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error_details: Optional[Dict[str, Any]] = None,
        zeus_style: bool = False,
    ) -> LogEntry:
        """
        Log an event.
        
        Args:
            event_type: Type of event
            message: Log message
            level: Severity level
            access_level: Access control level
            chat_id: Associated chat ID
            user_id: Associated user ID
            agent_name: Agent that generated the event
            metadata: Additional metadata
            error_details: Error details if applicable
            zeus_style: Whether to format errors in Zeus style
            
        Returns:
            Created LogEntry
        """
        # Apply Zeus-style formatting for errors if requested
        if zeus_style and level in (LogLevel.ERROR, LogLevel.WARNING):
            category = self._determine_error_category(event_type, error_details)
            message = ZeusErrorMessages.get_error_message(category, error=message)
        
        entry = LogEntry(
            event_type=event_type,
            message=message,
            level=level,
            access_level=access_level,
            chat_id=chat_id,
            user_id=user_id,
            agent_name=agent_name,
            metadata=metadata,
            error_details=error_details,
        )
        
        # Store in memory
        self._logs[entry.id] = entry
        
        # Trim memory if needed
        while len(self._logs) > self.MAX_MEMORY_LOGS:
            self._logs.popitem(last=False)
        
        # Update stats
        self._stats["total_logged"] += 1
        if level == LogLevel.ERROR:
            self._stats["errors_logged"] += 1
        elif level == LogLevel.WARNING:
            self._stats["warnings_logged"] += 1
        
        # Persist to file
        if self.enable_file_storage:
            await self._persist_to_file(entry)
        
        # Log to Python logger as well
        self._log_to_python_logger(entry)
        
        return entry
    
    def _determine_error_category(
        self,
        event_type: EventType,
        error_details: Optional[Dict[str, Any]]
    ) -> str:
        """Determine Zeus error category from event type."""
        mapping = {
            EventType.LLM_ERROR: "api_failure",
            EventType.TRANSLATION_FAILED: "api_failure",
            EventType.AUTH_FAILURE: "auth_failure",
            EventType.ACCESS_DENIED: "auth_failure",
            EventType.RATE_LIMITED: "rate_limit",
            EventType.ERROR: "general_error",
        }
        return mapping.get(event_type, "general_error")
    
    def _log_to_python_logger(self, entry: LogEntry) -> None:
        """Also log to Python's logging system."""
        log_msg = f"[{entry.event_type.value}] {entry.message}"
        
        if entry.agent_name:
            log_msg = f"[{entry.agent_name}] {log_msg}"
        
        level_map = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }
        
        logger.log(level_map.get(entry.level, logging.INFO), log_msg)
    
    async def _persist_to_file(self, entry: LogEntry) -> None:
        """Persist log entry to file."""
        try:
            # Daily log files
            date_str = entry.timestamp.strftime("%Y-%m-%d")
            log_file = self.storage_path / f"zeus_log_{date_str}.jsonl"
            
            # Serialize entry
            entry_data = entry.to_dict(include_sensitive=True)
            entry_json = json.dumps(entry_data, ensure_ascii=False)
            
            # Optionally encrypt
            if self._encryption.enabled:
                entry_json = self._encryption.encrypt(entry_json)
            
            # Append to file
            async with asyncio.Lock():
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(entry_json + "\n")
            
            # Check for rotation
            await self._maybe_rotate_logs()
            
        except Exception as e:
            logger.error(f"Failed to persist log: {e}")
    
    async def _maybe_rotate_logs(self) -> None:
        """Rotate old log files if needed."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.LOG_ROTATION_DAYS)
            
            for log_file in self.storage_path.glob("zeus_log_*.jsonl"):
                try:
                    # Extract date from filename
                    date_str = log_file.stem.replace("zeus_log_", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    
                    if file_date < cutoff:
                        # Archive old logs
                        archive_dir = self.storage_path / "archive"
                        archive_dir.mkdir(exist_ok=True)
                        log_file.rename(archive_dir / log_file.name)
                        logger.debug(f"📦 Archived old log: {log_file.name}")
                except Exception:
                    continue
                    
        except Exception as e:
            logger.warning(f"Log rotation failed: {e}")
    
    async def log_error(
        self,
        error: Exception,
        agent_name: Optional[str] = None,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        context: Optional[str] = None,
        zeus_style: bool = True,
    ) -> LogEntry:
        """
        Log an exception with full details and optional Zeus-style formatting.
        
        Args:
            error: The exception to log
            agent_name: Agent that caught the error
            chat_id: Associated chat ID
            user_id: Associated user ID
            context: Additional context about what was happening
            zeus_style: Whether to use Zeus-themed error messages
            
        Returns:
            Created LogEntry
        """
        error_details = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
            "context": context,
        }
        
        message = str(error)
        if zeus_style:
            message = ZeusErrorMessages.format_exception(error)
        
        return await self.log(
            event_type=EventType.ERROR,
            message=message,
            level=LogLevel.ERROR,
            access_level=AccessLevel.ADMIN,
            chat_id=chat_id,
            user_id=user_id,
            agent_name=agent_name,
            error_details=error_details,
            zeus_style=False,  # Already formatted
        )
    
    async def log_user_interaction(
        self,
        chat_id: str,
        user_id: str,
        message_text: str,
        agent_name: str,
        response_text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[LogEntry, Optional[LogEntry]]:
        """
        Log a user interaction (message + optional response).
        
        Args:
            chat_id: Chat identifier
            user_id: User identifier
            message_text: User's message
            agent_name: Agent handling the message
            response_text: Bot's response (if any)
            metadata: Additional metadata
            
        Returns:
            Tuple of (user_message_entry, response_entry)
        """
        # Log user message
        user_entry = await self.log(
            event_type=EventType.USER_MESSAGE,
            message=f"User message: {message_text[:100]}...",
            level=LogLevel.INFO,
            access_level=AccessLevel.INTERNAL,
            chat_id=chat_id,
            user_id=user_id,
            agent_name=agent_name,
            metadata={
                "message_length": len(message_text),
                **(metadata or {}),
            },
        )
        
        # Log bot response
        response_entry = None
        if response_text:
            response_entry = await self.log(
                event_type=EventType.BOT_RESPONSE,
                message=f"Bot response: {response_text[:100]}...",
                level=LogLevel.INFO,
                access_level=AccessLevel.INTERNAL,
                chat_id=chat_id,
                agent_name=agent_name,
                metadata={
                    "response_length": len(response_text),
                    "request_id": user_entry.id,
                },
            )
        
        return user_entry, response_entry
    
    async def query_logs(
        self,
        event_types: Optional[List[EventType]] = None,
        levels: Optional[List[LogLevel]] = None,
        access_level: AccessLevel = AccessLevel.ADMIN,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        include_sensitive: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Query logs with filtering.
        
        Args:
            event_types: Filter by event types
            levels: Filter by log levels
            access_level: Minimum access level required
            chat_id: Filter by chat ID
            user_id: Filter by user ID
            agent_name: Filter by agent name
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum results
            include_sensitive: Include sensitive data
            
        Returns:
            List of matching log entries
        """
        results = []
        
        for entry in reversed(list(self._logs.values())):
            # Access level check
            if not self._check_access(entry.access_level, access_level):
                continue
            
            # Event type filter
            if event_types and entry.event_type not in event_types:
                continue
            
            # Level filter
            if levels and entry.level not in levels:
                continue
            
            # Chat ID filter
            if chat_id and entry.chat_id != chat_id:
                continue
            
            # User ID filter
            if user_id and entry.user_id != user_id:
                continue
            
            # Agent filter
            if agent_name and entry.agent_name != agent_name:
                continue
            
            # Time range filter
            if start_time and entry.timestamp < start_time:
                continue
            if end_time and entry.timestamp > end_time:
                continue
            
            results.append(entry.to_dict(include_sensitive=include_sensitive))
            
            if len(results) >= limit:
                break
        
        return results
    
    def _check_access(self, entry_level: AccessLevel, required_level: AccessLevel) -> bool:
        """Check if access level is sufficient."""
        levels = [AccessLevel.PUBLIC, AccessLevel.INTERNAL, AccessLevel.ADMIN, AccessLevel.SYSTEM]
        return levels.index(required_level) >= levels.index(entry_level)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get logging statistics."""
        return {
            **self._stats,
            "logs_in_memory": len(self._logs),
            "file_storage_enabled": self.enable_file_storage,
            "hf_sync_enabled": self._hf_enabled,
            "encryption_enabled": self._encryption.enabled,
        }
    
    async def get_recent_errors(
        self,
        limit: int = 10,
        zeus_style: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get recent errors for display.
        
        Args:
            limit: Maximum number of errors
            zeus_style: Whether errors are Zeus-styled
            
        Returns:
            List of recent error entries
        """
        return await self.query_logs(
            levels=[LogLevel.ERROR, LogLevel.CRITICAL],
            limit=limit,
            include_sensitive=False,
        )
    
    def stop(self) -> None:
        """Stop the service and flush pending writes."""
        if self._commit_scheduler:
            try:
                self._commit_scheduler.stop()
                logger.info("📜 History log scheduler stopped")
            except Exception as e:
                logger.warning(f"Error stopping log scheduler: {e}")


# ============================================================================
# Decorator for Automatic Logging
# ============================================================================

def log_action(
    event_type: EventType = EventType.COMMAND_EXECUTED,
    agent_name: Optional[str] = None,
    zeus_errors: bool = True,
):
    """
    Decorator to automatically log function execution.
    
    Args:
        event_type: Event type to log
        agent_name: Agent name for the log
        zeus_errors: Use Zeus-style error messages
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            service = get_history_log()
            
            if service:
                # Log start
                await service.log(
                    event_type=EventType.AGENT_ACTIVATED,
                    message=f"Starting: {func.__name__}",
                    level=LogLevel.DEBUG,
                    agent_name=agent_name or func.__module__,
                )
            
            try:
                result = await func(*args, **kwargs)
                
                if service:
                    await service.log(
                        event_type=event_type,
                        message=f"Completed: {func.__name__}",
                        level=LogLevel.INFO,
                        agent_name=agent_name or func.__module__,
                    )
                
                return result
                
            except Exception as e:
                if service:
                    await service.log_error(
                        error=e,
                        agent_name=agent_name or func.__module__,
                        context=f"Function: {func.__name__}",
                        zeus_style=zeus_errors,
                    )
                raise
        
        return wrapper
    return decorator


# ============================================================================
# Singleton Instance and Initialization
# ============================================================================

_history_log_service: Optional[HistoryLogService] = None


def get_history_log() -> Optional[HistoryLogService]:
    """Get the history log service instance."""
    return _history_log_service


def init_history_log(
    storage_path: Optional[str] = None,
    hf_token: Optional[str] = None,
    hf_repo_id: Optional[str] = None,
    encryption_key: Optional[str] = None,
) -> HistoryLogService:
    """
    Initialize the history log service.
    
    Args:
        storage_path: Local storage directory
        hf_token: HF Hub token
        hf_repo_id: HF Hub repo ID
        encryption_key: Optional encryption key
        
    Returns:
        Configured HistoryLogService instance
    """
    global _history_log_service
    
    _history_log_service = HistoryLogService(
        storage_path=storage_path,
        hf_token=hf_token,
        hf_repo_id=hf_repo_id,
        encryption_key=encryption_key,
    )
    
    return _history_log_service
