from pydantic import ValidationError
import pytest

from src.config import Settings


def test_is_convex_configured_requires_url_and_sync_token() -> None:
    configured = Settings(
        _env_file=None,
        convex_deployment_url="https://convex.example.site",
        convex_sync_token="sync-token-123",
    )
    missing_token = Settings(
        _env_file=None,
        convex_deployment_url="https://convex.example.site",
        convex_sync_token=None,
    )
    missing_url = Settings(
        _env_file=None,
        convex_deployment_url=None,
        convex_sync_token="sync-token-123",
    )

    assert configured.is_convex_configured() is True
    assert missing_token.is_convex_configured() is False
    assert missing_url.is_convex_configured() is False


def test_is_convex_primary_backend_normalizes_valid_value() -> None:
    settings = Settings(_env_file=None, persistence_backend="  ConVex  ")

    assert settings.persistence_backend == "convex"
    assert settings.is_convex_primary_backend() is True


def test_is_convex_primary_backend_uses_local_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.is_convex_primary_backend() is False


def test_google_translate_config_compatibility_surface() -> None:
    configured = Settings(
        _env_file=None,
        google_translate_api_key="google-api-key-123",
    )
    missing_key = Settings(_env_file=None, google_translate_api_key=None)

    assert configured.google_translate_api_key == "google-api-key-123"
    assert configured.is_google_translate_configured() is True
    assert missing_key.is_google_translate_configured() is False


def test_llm_prompt_defaults_to_ms_green_persona() -> None:
    settings = Settings(_env_file=None)

    assert "Ms. Green" in settings.llm_system_prompt
    assert settings.is_zeus_allowed_in_group("G1", None, False) is True
    assert settings.is_zeus_allowed_in_group(None, "R1", False) is True


@pytest.mark.parametrize("value", ["", "remote", " convex-local "])
def test_persistence_backend_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValidationError, match="persistence_backend"):
        Settings(_env_file=None, persistence_backend=value)


@pytest.mark.parametrize(
    "value",
    [
        "convex.example.site",
        "ftp://convex.example.site",
        "not-a-url",
    ],
)
def test_convex_deployment_url_requires_http_or_https(value: str) -> None:
    with pytest.raises(ValidationError, match="convex_deployment_url"):
        Settings(_env_file=None, convex_deployment_url=value)