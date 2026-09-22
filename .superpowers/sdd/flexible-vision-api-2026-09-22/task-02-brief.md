### Task 2: Stop the log floods and the key leak (F1 + F2)

**Files:**
- Create: `src/utils/logging_hygiene.py`
- Create: `tests/test_logging_hygiene.py`
- Modify: `src/main.py` (call it right after `logging.basicConfig`)

**Interfaces:**
- Produces: `NOISY_LOGGERS: tuple[str, ...]` and `silence_noisy_loggers() -> None`. `main.py` calls it at import time. Root/app log level behaviour is unchanged (`settings.debug` still increases app verbosity); only third-party loggers are capped at WARNING. This is what stops `httpx` from writing full request URLs (the exchange-rate key path) into public run logs.

- [ ] **Step 1: Write the failing test**

`tests/test_logging_hygiene.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_logging_hygiene.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.utils.logging_hygiene'`.

- [ ] **Step 3: Implement `src/utils/logging_hygiene.py`**

```python
"""Log-noise control for third-party libraries.

The HF Space runs with DEBUG enabled in production, which floods the run log
with per-byte hpack/httpcore traces (739 of 968 captured lines on 2026-09-22)
and, worse, httpx's INFO request lines that embed full URLs — including API
keys passed as path segments (e.g. exchangerate-api v6). These loggers are
capped at WARNING regardless of the app-level log level; application loggers
keep their configured verbosity.
"""

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
    """Cap third-party loggers at WARNING so run logs stay readable and secret-free."""
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
```

- [ ] **Step 4: Wire it into `src/main.py`**

After the `logger = logging.getLogger(__name__)` line (below the existing `logging.basicConfig(...)` block at the top of the file), add:

```python
from src.utils.logging_hygiene import silence_noisy_loggers

# Keep production run logs readable (and free of key-bearing URLs): the
# third-party loggers listed in logging_hygiene are capped at WARNING.
silence_noisy_loggers()
```

Place the import with the other `src.utils` imports and the call immediately after the module logger is created.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_logging_hygiene.py tests/test_main.py -v
```

Expected: PASS. (`test_main` exercises the import path end-to-end.)

- [ ] **Step 6: Commit**

```bash
git add src/utils/logging_hygiene.py tests/test_logging_hygiene.py src/main.py
git commit -m "fix(logging): cap third-party loggers at WARNING; stop URL/key leakage into run logs"
```

### Verify Visual & Transform Claims (Task 2)

- [ ] **Visual claim:** the next deployed run log contains zero `hpack` / `filelock` / `httpcore` lines and no `v6/` exchange-rate URL.
- [ ] **Transform claim:** 195 KB → (expected) a few KB of app-level logs for the same traffic window.
- [ ] **Verification method:** re-pull `/logs/run` after deploy (Task 12 step "log check"), grep for `hpack|filelock|v6/`.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

### Task 3: RSS 451/4xx degrades quietly (F3)

**Files:**
- Modify: `src/services/news_data_service.py` (`_parse_rss_feed`, around line 249)
- Create: `tests/test_news_rss_fallback.py`

**Interfaces:**
- Produces: `_parse_rss_feed(url)` returns the fallback item list on any failure; HTTP-status failures log at WARNING without traceback, unexpected parse failures stay at ERROR with traceback. `NewsDataService._rss_fallback_items()` is a new static helper.

- [ ] **Step 1: Write the failing test**

`tests/test_news_rss_fallback.py`:

```python
"""HTTP-status RSS failures degrade quietly; malformed feeds stay loud."""

import httpx
import pytest

from src.services.news_data_service import NewsDataService


class _RaisingClient:
    def __init__(self, status_code: int):
        self._status = status_code

    async def get(self, url, timeout=None, follow_redirects=None):
        request = httpx.Request("GET", url)
        response = httpx.Response(self._status, request=request)
        raise httpx.HTTPStatusError("blocked", request=request, response=response)


@pytest.mark.asyncio
async def test_rss_http_error_logs_warning_not_error(caplog):
    service = NewsDataService(http_client=None, news_api_key=None)
    service.client = _RaisingClient(451)

    with caplog.at_level("WARNING"):
        items = await service._parse_rss_feed("https://www.bangkokpost.com/rss/data/thailand.xml")

    assert items[0]["title"] == "News unavailable"
    assert any("RSS feed unavailable (HTTP 451)" in record.message for record in caplog.records)
    assert not any(record.levelname == "ERROR" for record in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_news_rss_fallback.py -v
```

Expected: FAIL — current code logs ERROR ("RSS parse error …") and there is no "RSS feed unavailable (HTTP 451)" message.

- [ ] **Step 3: Implement** — replace the `except` block in `_parse_rss_feed`:

```python
        except httpx.HTTPStatusError as e:
            # Feed-side blocks (e.g. Bangkok Post returns 451 "Unavailable For
            # Legal Reasons" to HF Space egress) are expected degradation, not
            # application errors: log once, quietly, and serve the fallback.
            logger.warning(f"📰 RSS feed unavailable (HTTP {e.response.status_code}) for {url}")
            return self._rss_fallback_items()
        except Exception as e:
            logger.error(f"📰 RSS parse error for {url}: {e}", exc_info=True)
