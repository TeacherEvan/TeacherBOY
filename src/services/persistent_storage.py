from pathlib import Path

PERSISTENT_MOUNT = Path("/data")


def get_persistent_path() -> Path:
    return PERSISTENT_MOUNT


def is_persistent_storage_available() -> bool:
    path = get_persistent_path()
    if not path.exists():
        return False
    try:
        test_file = path / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return True
    except Exception:
        return False


def get_storage_subdir(name: str) -> Path:
    base = get_persistent_path() if is_persistent_storage_available() else Path("./data")
    subdir = base / name
    subdir.mkdir(parents=True, exist_ok=True)
    return subdir
