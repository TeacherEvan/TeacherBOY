# tests/test_config.py
import pytest


def test_images_hf_repo_id_field_exists():
    from src.config import Settings

    s = Settings()
    assert hasattr(s, "images_hf_repo_id")
    assert hasattr(s, "images_hf_enabled")


def test_evilevan_validator_rejects_wrong_prefix():
    from pydantic import ValidationError

    from src.config import Settings

    with pytest.raises(ValidationError):
        Settings(images_hf_repo_id="otheruser/bot-images")


def test_evilevan_validator_accepts_correct_prefix():
    from src.config import Settings

    s = Settings(images_hf_repo_id="EvilEvan/teacherboy-images")
    assert s.images_hf_repo_id == "EvilEvan/teacherboy-images"


def test_validator_applies_to_all_hf_repos():
    from pydantic import ValidationError

    from src.config import Settings

    for field in [
        "hf_memory_repo_id",
        "document_hf_repo_id",
        "history_log_hf_repo_id",
        "calendar_hf_repo_id",
        "images_hf_repo_id",
    ]:
        with pytest.raises(ValidationError):
            Settings(**{field: "baduser/bad-repo"})


def test_external_api_token_falls_back_to_budgetboss_token(monkeypatch):
    from src.config import Settings

    monkeypatch.setenv("BUDGETBOSS_SYNC_TOKEN", "bb-token")
    monkeypatch.delenv("EXTERNAL_API_TOKEN", raising=False)
    assert Settings().get_external_api_token() == "bb-token"
    monkeypatch.setenv("EXTERNAL_API_TOKEN", "ext-token")
    assert Settings().get_external_api_token() == "ext-token"


def test_external_api_image_hosts_parses_extras(monkeypatch):
    from src.config import Settings

    monkeypatch.setenv("EXTERNAL_API_IMAGE_HOSTS", "cdn.example.com, img.example.org")
    assert Settings().get_external_api_image_hosts() == {"cdn.example.com", "img.example.org"}


def test_external_api_defaults():
    from src.config import Settings

    s = Settings()
    assert s.external_api_enabled is True
    assert s.external_api_rate_limit_per_minute == 30
    assert s.external_api_max_image_mb == 6.0
    assert s.external_api_timeout_seconds == 60.0
