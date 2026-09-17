"""Optional local templates — prefer LLM for most topics now."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_PATH = ROOT / "data" / "sensitive_templates.json"

# Empty by default: let Gemini answer with full dialog context + sales prompt.
# Override via data/sensitive_templates.json if needed.
DEFAULT_TEMPLATES: list[dict] = []


def _load() -> list[dict]:
    if TEMPLATES_PATH.exists():
        try:
            data = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return DEFAULT_TEMPLATES


def match_sensitive(text: str) -> str | None:
    lower = text.lower()
    for item in _load():
        for pat in item.get("patterns", []):
            if pat.lower() in lower:
                responses = item.get("responses") or []
                if responses:
                    import random

                    return random.choice(responses)
    return None


def is_voice_ok_question(text: str) -> bool:
    return bool(
        re.search(r"можно\s+(гс|голос|voice|аудио)", text.lower())
        or re.search(r"голосов(ое|ые|ым)", text.lower())
    )


VOICE_OK_REPLIES = [
    "да, без проблем",
    "да, кидайте гс",
    "конечно, голосовые ок",
]
