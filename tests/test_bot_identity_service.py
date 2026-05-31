from pathlib import Path

from src.services.bot_identity_service import BotIdentityService


def test_identity_service_loads_defaults_when_state_missing(tmp_path: Path):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Ms. Green",
        default_aliases=[
            "ms. green",
            "ms green",
        ],
    )

    profile = service.get_profile()

    assert profile.display_name == "Ms. Green"
    assert "ms. green" in profile.aliases
    assert "ms green" in profile.aliases


def test_identity_service_preserves_old_name_as_alias_on_rename(
    tmp_path: Path,
):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Ms. Green",
        default_aliases=["ms. green"],
    )

    updated = service.update_identity("Ms. Green", ["ms green"])

    assert updated.display_name == "Ms. Green"
    assert "ms. green" in updated.aliases
    assert "ms green" in updated.aliases


def test_split_command_prefix_supports_ms_green(tmp_path: Path):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Ms. Green",
        default_aliases=["ms. green", "ms green", "green"],
    )

    prefix, rest = service.split_command_prefix("Ms. Green search python")

    assert prefix == "ms. green"
    assert rest == "search python"


def test_split_command_prefix_rejects_legacy_zeus_after_cutover(tmp_path: Path):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Ms. Green",
        default_aliases=["ms. green", "ms green", "green"],
    )

    prefix, rest = service.split_command_prefix("Zeus search python")

    assert prefix is None
    assert rest == "Zeus search python"
