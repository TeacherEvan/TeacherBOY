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
