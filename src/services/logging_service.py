import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger as _logger

from src.utils.correlation import get_correlation_id


class LoggingService:
    def __init__(self, log_dir: Path | str = Path("./data/logs"), log_file: str = "ms_green.log") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / log_file
        self._stderr_handler_active = False

        _logger.remove()
        _logger.add(
            str(self.log_file),
            level="INFO",
            rotation="50 MB",
            retention="7 days",
            format="{message}",
        )
        if not getattr(LoggingService, "_stderr_handler_active", False):
            LoggingService._stderr_handler_active = True
            _logger.add(
                sys.stderr,
                level="INFO",
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {message}",
                colorize=True,
            )

    @staticmethod
    def _build_payload(level: str, message: str, extra: dict | None = None) -> str:
        payload: dict[str, object] = {
            "level": level,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
            "correlation_id": get_correlation_id(),
        }
        if extra:
            payload["extra"] = extra
        return json.dumps(payload, ensure_ascii=False)

    def info(self, message: str, extra: dict | None = None) -> None:
        _logger.info(self._build_payload("INFO", message, extra))

    def warning(self, message: str, extra: dict | None = None) -> None:
        _logger.warning(self._build_payload("WARNING", message, extra))

    def error(self, message: str, extra: dict | None = None) -> None:
        _logger.error(self._build_payload("ERROR", message, extra))

    def debug(self, message: str, extra: dict | None = None) -> None:
        _logger.debug(self._build_payload("DEBUG", message, extra))

logging_service = LoggingService()
