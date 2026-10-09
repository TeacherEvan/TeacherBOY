
- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_main.py -v
```

Expected: PASS — including the pre-existing health/readiness tests.

- [ ] **Step 5: Write `docs/EXTERNAL_API.md`**

````markdown
# External Vision API

Token-protected endpoints for other projects to run image analysis on the
TeacherBOY Space. Additive to the LINE bot — the webhook flow is untouched.

Base URL: `https://evilevan-teacherboy.hf.space`

## Auth

Every `/api/v1/*` request needs a Bearer token:

- `EXTERNAL_API_TOKEN` Space secret, or
- `BUDGETBOSS_SYNC_TOKEN` as fallback (so Budget Boss keeps working without changes).

## Tasks

| task | what it returns |
|---|---|
| `receipt` | extracted text + OcrPayload (`engine: "gemini-vision@1"`, line list) for finance ingestion |
| `article` | strict JSON (title, publication, date, byline, summary, key_points, language) in `structured` |
| `news` | strict JSON (headline, source, date, top_facts, why_it_matters, entities, language) in `structured` |
| `ocr` | raw extracted text (signs, menus, documents, screenshots) |
| `general` | open description; pass `prompt` for a specific question |

## Request

`POST /api/v1/analyze` — JSON body:

```json
{
  "image": { "base64": "<raw base64>" },
  "task": "receipt",
  "countryHint": "TH"
}
```

`image` accepts exactly one of: `dataUrl` (a `data:image/...;base64,...` string),
`base64` (raw base64; MIME sniffed automatically), or `url` (HTTPS only;
host must be on the SSRF allowlist — `huggingface.co` and friends are built in,
extend via the `EXTERNAL_API_IMAGE_HOSTS` secret, comma-separated).

Optional: `prompt` (≤4000 chars, replaces the task's default prompt).

## Response

```json
{
  "success": true,
  "requestId": "0f3a9c2b7d1e4a55",
  "bytes": 182233,
  "task": "receipt",
  "text": "COFFEE 45 THB\nTOTAL 45",
  "structured": null,
  "ocr": { "engine": "gemini-vision@1", "lines": [ ... ] },
  "provider": "gemini",
  "latency_ms": 2340
}
```

## Errors

| status | meaning |
|---|---|
| 400 | bad input (invalid base64, both/neither image source, non-allowlisted URL, non-image content type) |
| 401 | missing/wrong Bearer token |
| 413 | image larger than `EXTERNAL_API_MAX_IMAGE_MB` (default 6 MB) |
| 422 | unknown task |
| 429 | per-IP rate limit (`EXTERNAL_API_RATE_LIMIT_PER_MINUTE`, default 30/min) |
| 502 | all vision providers failed |
| 504 | analysis exceeded `EXTERNAL_API_TIMEOUT_SECONDS` (default 60 s) |
| 503 | API disabled / no token configured / no vision provider |

## Examples

```bash
# List tasks
curl -s https://evilevan-teacherboy.hf.space/api/v1/tasks \
  -H "Authorization: Bearer $EXTERNAL_API_TOKEN"

# Scrape a receipt (base64)
B64=$(base64 -w0 receipt.jpg)
curl -s -X POST https://evilevan-teacherboy.hf.space/api/v1/analyze \
  -H "Authorization: Bearer $EXTERNAL_API_TOKEN" -H "Content-Type: application/json" \
  -d "{\"image\":{\"base64\":\"$B64\"},\"task\":\"receipt\",\"countryHint\":\"TH\"}"

# Article screenshot → structured JSON
curl -s -X POST https://evilevan-teacherboy.hf.space/api/v1/analyze \
  -H "Authorization: Bearer $EXTERNAL_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"image":{"url":"https://huggingface.co/datasets/EvilEvan/teacherboy-images/resolve/main/sample.png"},"task":"article"}'
```

```python
# Python (requests)
import base64, requests

with open("receipt.jpg", "rb") as fh:
    b64 = base64.b64encode(fh.read()).decode()

resp = requests.post(
    "https://evilevan-teacherboy.hf.space/api/v1/analyze",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"image": {"base64": b64}, "task": "receipt", "countryHint": "TH"},
    timeout=90,
)
resp.raise_for_status()
print(resp.json()["ocr"]["lines"][:3])
```
````

Add to `README.md` (in the features/endpoints section, next to the webhook/health mentions):

```markdown
- **External Vision API** (`/api/v1/analyze`, `/api/v1/tasks`) — token-protected image
  analysis for other projects (receipts, articles, news, OCR). See
  [docs/EXTERNAL_API.md](docs/EXTERNAL_API.md).
```

- [ ] **Step 6: Run the full local gate**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/
pytest tests/test_main.py tests/test_external_vision_api.py tests/services/test_external_vision_service.py -v
```

Expected: clean + PASS.

- [ ] **Step 7: Commit**

```bash
git add src/main.py tests/test_main.py docs/EXTERNAL_API.md README.md
git commit -m "feat(api): mount /api/v1 vision router; document external integration"
```

### Verify Visual & Transform Claims (Task 9)

- [ ] **Visual claim:** `GET /` on the deployed Space still 200; `GET /api/v1/tasks` 200 with token, 401 without.
- [ ] **Transform claim:** `/health` JSON now includes `checks.external_api.enabled`.
- [ ] **Verification method:** Task 10 live smoke tests (curl).
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]
