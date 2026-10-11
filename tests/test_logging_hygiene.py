"""Third-party loggers must never flood (or leak URLs into) production logs."""

import logging

from src.utils.logging_hygiene import NOISY_LOGGERS, silence_noisy_loggers


def test_noisy_loggers_capped_at_warning():
    silence_noisy_loggers()
    for name in NOISY_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


def test_httpx_cannot_emit_info_request_lines():
    silence_noisy_loggers()
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
