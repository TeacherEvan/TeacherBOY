import asyncio
import os
from pathlib import Path

REPO = Path("/home/ewaldt/Documents/VS/Other/Bot/TeacherBOY")
os.environ.setdefault("PYTHONPATH", str(REPO / "src"))

from src.services.ai_translation_service import AITranslationService  # noqa: E402


async def main():
    svc = AITranslationService()
    cases = [
        ("สวัสดี", "th", "en"),
        ("Hello world", "en", "th"),
    ]
    for text, src, tgt in cases:
        print(f"--- translate {src}->{tgt}: {text!r}")
        res = await svc.translate(text, source_lang=src, target_lang=tgt)
        print("RESULT:", repr(res))


asyncio.run(main())
