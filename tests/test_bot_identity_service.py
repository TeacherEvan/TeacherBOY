from pathlib import Path

from src.services.bot_identity_service import BotIdentityService


def test_identity_service_loads_defaults_when_state_missing(tmp_path: Path):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="KPS-Assistant",
        default_aliases=["kps", "lps-assistant", "hey", "bud", "buddy", "zeus"],
    )

    profile = service.get_profile()

    assert profile.display_name == "KPS-Assistant"
    assert "kps" in profile.aliases
    assert "zeus" in profile.aliases


def test_identity_service_preserves_old_name_as_alias_on_rename(tmp_path: Path):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Zeus",
        default_aliases=["zeus"],
    )

    updated = service.update_identity("KPS-Assistant", ["kps", "buddy"])

    assert updated.display_name == "KPS-Assistant"
    assert "zeus" in updated.aliases
    assert "kps" in updated.aliases