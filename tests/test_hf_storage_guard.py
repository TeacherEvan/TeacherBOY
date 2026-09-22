"""HF storage guard tests."""
from src.services.hf_storage_mixin import HFStorageMixin


class _DummyStorage(HFStorageMixin):
    pass

def test_stale_cache_is_removed_from_sync_folder(tmp_path):
    dummy = _DummyStorage()
    dummy._hf_sync_folder = tmp_path / "conversations"
    stale = dummy._hf_sync_folder / ".cache" / "huggingface" / "download"
    stale.mkdir(parents=True)
    (stale / "junk.metadata").write_text("x")
    dummy._heal_stale_cache()
    assert not (dummy._hf_sync_folder / ".cache").exists()

def test_heal_is_a_noop_when_no_cache_exists(tmp_path):
    dummy = _DummyStorage()
    dummy._hf_sync_folder = tmp_path / "clean"
    dummy._hf_sync_folder.mkdir()
    dummy._heal_stale_cache()
