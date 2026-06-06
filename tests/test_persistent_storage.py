import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services.persistent_storage import get_persistent_path, get_storage_subdir, is_persistent_storage_available


def test_get_persistent_path_returns_data_dir():
    assert get_persistent_path() == Path("/data")


def test_is_persistent_storage_available_with_existing_dir(tmp_path: Path, monkeypatch):
    active = tmp_path / ".write_test"
    active.write_text("ok", encoding="utf-8")
    monkeypatch.setattr("services.persistent_storage.get_persistent_path", lambda: tmp_path)
    assert is_persistent_storage_available() is True


def test_get_storage_subdir_falls_back_when_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("services.persistent_storage.is_persistent_storage_available", lambda: False)
    monkeypatch.setattr("services.persistent_storage.get_persistent_path", lambda: Path("/nonexistent_xyz"))
    result = get_storage_subdir("conversations")
    assert result.exists()
