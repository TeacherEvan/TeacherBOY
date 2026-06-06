#!/usr/bin/env bash
set -euo pipefail
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
sed -i -E 's/^GOOGLE_TRANSLATE_API_KEY=.*/GOOGLE_TRANSLATE_API_KEY=***                    Leave Google disabled until you put a real AIza... key here" is what failed. But that still won’t disable it…unless replace_with_empty is set.replace_with_empty = True                    sed -i -E 's/^(GOOGLE_TRANSLATE_API_KEY=).*/\1/' .env
sed -i -E 's/^OPENROUTER_DEFAULT_MODEL=.*/OPENROUTER_DEFAULT_MODEL=meta-llama\/llama-3.1-8b-instruct:free/' .env
sed -i -E 's/^HERMES_(BASE_URL|API_KEY|MODEL)=.*/HERMES_\1=/' .env || true
python3 - <<'PY'
from pathlib import Path
p = Path('.env')
text = p.read_text()
text = text.replace('LIBRETRANSLATE_API_KEY=*** Translation Performance Optimization', 'LIBRETRANSLATE_API_KEY=*** first-platform = "terminal"                    p.write_text(text)
PY
