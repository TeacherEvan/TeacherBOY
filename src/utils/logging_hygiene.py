"""Log-noise control for third-party libraries."""

import logging

NOISY_LOGGERS: tuple[str, ...] = (
    "hpack",
    "hpack.hpack",
    "httpcore",
    "httpcore.http2",
    "httpcore.http11",
    "httpcore.connection",
    "httpx",
    "filelock",
    "urllib3",
)


def silence_noisy_loggers() -> None:
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
