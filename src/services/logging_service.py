import json
import sys
from pathlib import Path
from loguru import logger as _logger


class LoggingService:
    def __init__(self, log_dir: Path | str = Path("./data/logs"), log_file: str = "ms_green.log") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / log_file

        _logger.remove()
        _logger.add(
            str(self.log_file),
            level="INFO",
            rotation="50 MB",
            retention="7 days",
            format="{message}",
        )
        _logger.add(
            sys.stderr,
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}",
        )

    def info(self, message: str, extra: dict | None = None) -> None:
        if extra:
            _logger.bind(**extra).info(json.dumps({"level": "INFO", "message": message}, ensure_ascii=False))
        else:
            _logger.info(json.dumps({"level": "INFO", "message": message}, ensure_ascii=False))

    def warning(self, message: str, extra: dict | None = None) -> None:
        if extra:
            _logger.bind(**extra).warning(json.dumps({"level": "WARNING", "message": message}, ensure_ascii=False))
        else:
            _logger.warning(json.dumps({"level": "WARNING", "message": message}, ensure_ascii=False))

    def error(self, message: str, extra: dict | None = None) -> None:
        if extra:
            _logger.bind(**extra).error(json.dumps({"level": "ERROR", "message": message}, ensure_ascii=False))
        else:
            _logger.error(json.dumps({"level": "ERROR", "message": message}, ensure_ascii=False))


logging_service = LoggingService()
