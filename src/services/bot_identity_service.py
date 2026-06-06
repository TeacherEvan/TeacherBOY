from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_BOT_IDENTITY_NAME = "Ms. Green"
DEFAULT_BOT_IDENTITY_ALIASES = [
    "ms. green",
    "ms green",
]


_bot_identity_service: BotIdentityService | None = None


@dataclass
class BotIdentityProfile:
    display_name: str
    aliases: list[str]


class BotIdentityService:
    def __init__(
        self,
        storage_path: Path,
        default_name: str,
        default_aliases: list[str],
    ):
        self._storage_path = Path(storage_path)
        self._default_name = default_name.strip()
        self._default_aliases = self._normalize(default_aliases + [default_name])
        self._profile = self._load()
        self._cached_recognition_aliases: list[str] | None = None

    def _normalize(self, aliases: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for alias in aliases:
            cleaned = (alias or "").strip().lower()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
        return result

    def _recognition_aliases(self) -> list[str]:
        """Aliases accepted for command-prefix recognition."""
        if self._cached_recognition_aliases is None:
            self._cached_recognition_aliases = self._normalize([self._profile.display_name, *self._profile.aliases])
        return self._cached_recognition_aliases

    def _load(self) -> BotIdentityProfile:
        if not self._storage_path.exists():
            return BotIdentityProfile(
                self._default_name,
                self._default_aliases,
            )

        data = json.loads(self._storage_path.read_text(encoding="utf-8"))
        return BotIdentityProfile(
            display_name=data["display_name"],
            aliases=self._normalize(data["aliases"]),
        )

    def _save(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps(asdict(self._profile), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_profile(self) -> BotIdentityProfile:
        return self._profile

    def update_identity(self, display_name: str, aliases: list[str]) -> BotIdentityProfile:
        previous_name = self._profile.display_name
        merged_aliases = self._normalize(aliases + [display_name, previous_name] + self._profile.aliases)
        self._profile = BotIdentityProfile(display_name=display_name.strip(), aliases=merged_aliases)
        self._cached_recognition_aliases = None  # Invalidate cache on profile change
        self._save()
        return self._profile

    def matches_prefix(self, token: str) -> bool:
        return (token or "").strip().lower() in self._recognition_aliases()

    def split_command_prefix(self, text: str) -> tuple[str | None, str]:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        if cleaned.startswith("/"):
            cleaned = cleaned[1:].lstrip()
        if not cleaned:
            return None, ""

        lowered = cleaned.lower()
        for alias in sorted(self._recognition_aliases(), key=len, reverse=True):
            if lowered == alias:
                return alias, ""
            if lowered.startswith(f"{alias} "):
                return alias, cleaned[len(alias) :].lstrip()
        return None, cleaned

    def expand_prefixed_trigger(self, trigger: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", (trigger or "").strip().lower())
        expansion_aliases = sorted(set(self._recognition_aliases()), key=len, reverse=True)

        for alias in expansion_aliases:
            if normalized == alias:
                return expansion_aliases.copy()
            if normalized.startswith(f"{alias} "):
                suffix = normalized[len(alias) :].lstrip()
                return [f"{candidate} {suffix}".strip() for candidate in expansion_aliases]

        return [normalized]


def configure_bot_identity_service(
    storage_path: str | Path,
    default_name: str,
    default_aliases: list[str],
) -> BotIdentityService:
    global _bot_identity_service
    _bot_identity_service = BotIdentityService(
        storage_path=Path(storage_path),
        default_name=default_name,
        default_aliases=default_aliases,
    )
    return _bot_identity_service


def get_bot_identity_service() -> BotIdentityService:
    global _bot_identity_service
    if _bot_identity_service is not None:
        return _bot_identity_service

    from src.config import settings as current_settings

    storage_path = getattr(current_settings, "bot_identity_storage_path", None)
    if not isinstance(storage_path, str) or not storage_path.strip():
        storage_path = "./data/bot_identity/profile.json"

    default_name = getattr(current_settings, "bot_identity_default_name", None)
    if not isinstance(default_name, str) or not default_name.strip():
        default_name = DEFAULT_BOT_IDENTITY_NAME

    raw_aliases = getattr(
        current_settings,
        "bot_identity_default_aliases",
        None,
    )
    if isinstance(raw_aliases, str) and raw_aliases.strip():
        default_aliases = [alias.strip() for alias in raw_aliases.split(",") if alias.strip()]
    else:
        default_aliases = DEFAULT_BOT_IDENTITY_ALIASES.copy()

    return configure_bot_identity_service(
        storage_path,
        default_name,
        default_aliases,
    )
