git mv temp_handler_code.txt docs/archive/2026-09/temp_handler_code.txt
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: drop stray pip artifacts; archive loose scratch files"
```

### Verify Visual & Transform Claims (Task 10)

- [ ] **Visual claim:** repo root no longer lists `=2.100.0,`, `=42.0.0`, or the loose `.txt` files.
- [ ] **Transform claim:** `git log --stat -1` shows renames + deletions.
- [ ] **Verification method:** `ls` + `git show --stat HEAD`.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

# Part C — Deploy & live verification

### Task 11: Deploy to the Space and verify end-to-end

**Files:** none (operational task).

**Interfaces:**
- Consumes: everything above, committed on `main`.

- [ ] **Step 1: Pre-flight gate**

```bash
cd /home/leandi-duplessis/github/workspaces/TeacherBOY
. .venv/bin/activate
ruff check src/ tests/ && ruff format --check src/ tests/
pytest -q 2>&1 | tail -5
git status --short   # expected: clean
```

Expected: lint clean; tests green (baseline parity with Task 0).

- [ ] **Step 2: Push to main (GitHub Actions deploys)**

```bash
git push origin main
```

Then watch the deploy:

```bash
gh run list --workflow ci.yml --limit 3
gh run watch "$(gh run list --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

If `gh` is unavailable, watch from the Actions tab in the browser. Expected: `lint-and-type` → `unit-test` → `docker-build` → `deploy` all green; `huggingface_sync.yml` also runs (repo variable `ENABLE_HF_SYNC=true`).

- [ ] **Step 3: Verify the Space picked up the new SHA**

```bash
python3 - <<'EOF'
import json, os, urllib.request

def get_sha():
    req = urllib.request.Request(
        "https://huggingface.co/api/spaces/EvilEvan/TeacherBOY",
        headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"},
    )
    return json.load(urllib.request.urlopen(req))["runtime"]["sha"]

print("space sha:", get_sha())
EOF
git rev-parse HEAD
```

Expected: Space SHA == `git rev-parse HEAD`; the Space rebuilds (~2–5 min). Poll the HF API until the new SHA is live and `runtime.stage == "RUNNING"`.

- [ ] **Step 4: Confirm the Space token**

Check `https://evilevan-teacherboy.hf.space/health`:

```bash
curl -s https://evilevan-teacherboy.hf.space/health | python3 -c "import json,sys; print(json.load(sys.stdin)['checks']['external_api'])"
```

Expected: `{'enabled': True}`. If `enabled: False`, set the Space secret (Settings → Variables and secrets):
`EXTERNAL_API_TOKEN = <a new random string>` (or rely on the existing `BUDGETBOSS_SYNC_TOKEN`). Re-check until true. **[Evan action — do not do this from a script.]**

- [ ] **Step 5: Auth + tasks smoke test**

```bash
TOKEN="$EXTERNAL_API_TOKEN"   # export locally = same value set in the Space
curl -s -o /dev/null -w "%{http_code}\n" https://evilevan-teacherboy.hf.space/api/v1/tasks            # expect 401
curl -s https://evilevan-teacherboy.hf.space/api/v1/tasks -H "Authorization: Bearer $TOKEN"          # expect 200 + task list
```

- [ ] **Step 6: Real OCR end-to-end (the money shot)**

Generate a tiny text image, POST it, assert the text comes back:

```bash
.venv/bin/python - <<'PY'
from PIL import Image, ImageDraw
img = Image.new("RGB", (720, 240), "white")
ImageDraw.Draw(img).text((30, 100), "FENRIE SMOKE TEST 45123", fill="black")
img.save("/tmp/smoke_ocr.png")
print("wrote /tmp/smoke_ocr.png")
PY
# PIL ships with the easyocr dependency; if missing: .venv/bin/pip install pillow

B64=$(base64 -w0 /tmp/smoke_ocr.png)
curl -s -X POST "https://evilevan-teacherboy.hf.space/api/v1/analyze" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"image\":{\"base64\":\"$B64\"},\"task\":\"ocr\"}" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['provider'], '|', d['text'][:200]); assert 'SMOKE' in d['text'].upper(), 'text not extracted'; print('OCR SMOKE: PASS')"
```

Expected: `provider` is a real model (gemini first), extracted text contains `SMOKE`, script prints `OCR SMOKE: PASS`.

- [ ] **Step 7: Log verification (transforms from Part A)**

```bash
curl -sN -H "Authorization: Bearer $HF_TOKEN" "https://huggingface.co/api/spaces/EvilEvan/TeacherBOY/logs/run" > /tmp/run_after.log &
PID=$!; sleep 40; kill $PID 2>/dev/null
python3 - <<'EOF'
lines = open("/tmp/run_after.log", errors="replace").read().splitlines()
for needle in ("hpack", "filelock", "httpcore", "Cannot add middleware", "v6/exchangerate"):
    hits = [l for l in lines if needle in l]
    print(f"{needle!r}: {len(hits)} hits")
api = [l for l in lines if "/api/v1/analyze" in l]
print("api log lines:", len(api))
EOF
```

Expected: 0 hits for all noise needles; ≥2 lines for `/api/v1/analyze` (the smoke test);

- [ ] **Step 8: Update `docs/recommendations.md`**

Append:

```markdown
## 2026-09-22 — Flexible Vision API (Fenrie)

- [R2] ✅ Implemented: `/api/v1/analyze` + `/api/v1/tasks` mounted in `src/main.py`
  (see `docs/EXTERNAL_API.md`, plan `docs/plans/2026-09-22-flexible-vision-api.md`).
- [R1] Superseded: other projects can now consume the Space directly, no provider re-config needed.
```

```bash
git add docs/recommendations.md
git commit -m "docs: mark vision endpoint recommendation as implemented"
git push origin main
```

