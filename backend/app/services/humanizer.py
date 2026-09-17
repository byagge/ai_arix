"""Post-process AI replies — human Telegram style per product spec."""
from __future__ import annotations

import random
import re


GREETING_ONLY = re.compile(
    r"^(привет|здравствуйте|здравствуй|добрый\s+(день|вечер|утро)|hi|hello|hey|салют|ку|хай)[\s!?.]*$",
    re.I,
)

GREETING_REPLIES = [
    "привет",
    "здравствуйте",
    "добрый день",
    "привет, слушаю",
    "здравствуйте, на связи",
]

_PRICE_LINE = re.compile(
    r"(?im)^.*(?:\b(?:\$|usd|usdt)\b|\bцен[аыуе]?\b|\bстоим|\bпрайс|\bот\s+\d|\b\d+\s*(?:usd|usdt|\$)).*$"
)
_ESCROW_PUSH = re.compile(
    r"(?i)(?:хотите\s+через\s+гарант|безопасн\w*\s+сделк|эскроу|escrow|"
    r"continental|lolzteam|через\s+гаранта\s*[-–,])"
)
_NARROW_SCOPE = re.compile(
    r"(?i)(?:мы\s+больше\s+по|не\s+наш\s+профиль|специализируемся\s+на|"
    r"обычно\s+делаем\s+только|это\s+не\s+наше)"
)
_DEFER_PRICE = re.compile(
    r"(?i)(?:по\s+цен[еы]\s+чуть\s+позже|сориентиру(?:ю|ем)\s+по\s+цен|"
    r"сначала\s+зафиксируем\s+объ[её]м|цен[уа]\s+позже\s+напиш)"
)


def is_greeting_only(text: str) -> bool:
    return bool(GREETING_ONLY.match(text.strip()))


def greeting_reply() -> str:
    return random.choice(GREETING_REPLIES)


STICKER_GREETING_REPLIES = [
    "привет, чем могу помочь? делаем любой софт под задачу - боты, утилиты, веб, парсеры",
    "здравствуйте, на связи, напишите что нужно сделать - софт, бот или утилиту под вашу задачу",
    "привет, слушаю, что нужно разработать?",
]


def sticker_greeting_reply() -> str:
    return random.choice(STICKER_GREETING_REPLIES)


def humanize_reply(text: str, tone: str = "human_coder") -> str:
    if not text:
        return text

    t = text.strip()
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"`(.+?)`", r"\1", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"^[-•]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\n{3,}", "\n\n", t)

    # Long dashes → hyphen
    t = t.replace("—", "-").replace("–", "-").replace("−", "-")

    # a/b alternatives → a или b (keep urls and paths)
    def _slash_fix(m: re.Match[str]) -> str:
        left, right = m.group(1), m.group(2)
        if left.lower() in ("http", "https") or right.startswith("/"):
            return m.group(0)
        return f"{left} или {right}"

    t = re.sub(r"(?<![:/\w])([A-Za-zА-Яа-яЁё0-9+]+)\s*/\s*([A-Za-zА-Яа-яЁё0-9+]+)", _slash_fix, t)

    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)

    # Drop robotic openers
    t = re.sub(r"^(?:понял(?:а|и)?[,!.]?\s*)+", "", t, flags=re.I)
    t = re.sub(r"^(?:конечно[,!.]?\s*)+", "", t, flags=re.I)
    t = re.sub(r"^(?:отличн\w+ вопрос[,!.]?\s*)+", "", t, flags=re.I)

    # Soften periods → commas occasionally (messenger feel), keep ? !
    def _soft_period(m: re.Match[str]) -> str:
        # keep short abbreviations-ish endings alone
        return ", "

    # Only replace mid-sentence periods when followed by capital/cyrillic capital (new sentence)
    t = re.sub(r"\.(?=\s+[A-ZА-ЯЁ])", ",", t)

    lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
    cleaned: list[str] = []
    dropped_narrow = False
    for ln in lines:
        if _NARROW_SCOPE.search(ln):
            dropped_narrow = True
            continue
        if _PRICE_LINE.search(ln) and not re.search(
            r"(?i)цен[уаые]\s+(?:чуть|позже|отдельн|скаж)", ln
        ):
            if re.search(r"\d", ln) and re.search(r"(?i)usd|usdt|\$|от\s+\d", ln):
                continue
        cleaned.append(ln)
    if cleaned:
        t = "\n".join(cleaned)
    elif dropped_narrow:
        t = "да, сделаем, напиши детали задачи"

    if _DEFER_PRICE.search(t):
        t = "уточни что именно нужно по задаче - цену скажу когда всё соберём"

    if _ESCROW_PUSH.search(t) and not re.search(r"(?i)да[, ]+можно|гарант\s*\+", t):
        parts = re.split(r"(?<=[.!?])\s+", t)
        parts = [p for p in parts if not _ESCROW_PUSH.search(p)]
        if parts:
            t = " ".join(parts)

    # Prefer lowercase start (human chat)
    if t and t[0].isupper() and not t.startswith(("USDT", "TRC", "API", "TRON", "HTTP")):
        if random.random() < 0.85:
            t = t[0].lower() + t[1:]

    t = t.strip(" ,")
    t = re.sub(r",{2,}", ",", t)
    t = re.sub(r"\s+,", ",", t)

    if not t:
        return "напишите что нужно - сделаем под задачу"
    return t


def expand_payment_placeholders(text: str, replacements: dict[str, str]) -> str:
    """Replace {usdt-tron}, {amount}, etc. without touching premium emoji entities."""
    out = text
    for key, val in replacements.items():
        out = out.replace(f"{{{key}}}", val)
    return out
