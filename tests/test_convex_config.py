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