from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
import re


DEFAULT_BOT_IDENTITY_NAME = "KPS-Assistant"
DEFAULT_BOT_IDENTITY_ALIASES = ["kps", "lps-assistant", "hey", "bud", "buddy", "zeus"]


_bot_identity_service: "BotIdentityService | None" = None


@dataclass
class BotIdentityProfile:
    display_name: str
    aliases: list[str]


class BotIdentityService:
    def __init__(self, storage_path: Path, default_name: str, default_aliases: list[str]):
        self._storage_path = Path(storage_path)
        self._default_name = default_name.strip()
        self._default_aliases = self._normalize(default_aliases + [default_name])
        self._profile = self._load()

    def _normalize(self, aliases: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for alias in aliases:
            cleaned = (alias or "").strip().lower()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
        return result

    def _load(self) -> BotIdentityProfile:
        if not self._storage_path.exists():
            return BotIdentityProfile(self._default_name, self._default_aliases)

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
        merged_aliases = self._normalize(
            aliases + [display_name, previous_name] + self._profile.aliases
        )
        self._profile = BotIdentityProfile(
            display_name=display_name.strip(), aliases=merged_aliases
        )
        self._save()
        return self._profile

    def matches_prefix(self, token: str) -> bool:
        return (token or "").strip().lower() in self._profile.aliases

    def split_command_prefix(self, text: str) -> tuple[str | None, str]:
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        if cleaned.startswith("/"):
            cleaned = cleaned[1:].lstrip()
        if not cleaned:
            return None, ""

        parts = cleaned.split(" ", 1)
        prefix = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""
        if self.matches_prefix(prefix):
            return prefix, rest
        return None, cleaned

    def expand_prefixed_trigger(self, trigger: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", (trigger or "").strip().lower())
        if not normalized.startswith("zeus "):
            return [normalized]

        suffix = normalized[5:]
        return [f"{alias} {suffix}".strip() for alias in self._profile.aliases]


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

    raw_aliases = getattr(current_settings, "bot_identity_default_aliases", None)
    if isinstance(raw_aliases, str) and raw_aliases.strip():
        default_aliases = [alias.strip() for alias in raw_aliases.split(",") if alias.strip()]
    else:
        default_aliases = DEFAULT_BOT_IDENTITY_ALIASES.copy()

    return configure_bot_identity_service(storage_path, default_name, default_aliases)