import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services.logging_service import LoggingService


def test_logging_service_creates_json_logs(tmp_path: Path):
    service = LoggingService(log_dir=tmp_path)
    service.info("test message", extra={"user_id": "U123"})

    log_file = tmp_path / "ms_green.log"
    assert log_file.exists()

    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1
    record = json.loads(lines[-1])
    assert record["message"] == "test message"
    assert record["level"] == "INFO"
