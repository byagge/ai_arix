"""Message classification + reply quality gate for consistently good sales replies."""
from __future__ import annotations

import random
import re
from enum import Enum


class MsgKind(str, Enum):
    GREETING = "greeting"
    SHORT_POINTER = "short_pointer"  # «тз вот», «вот» pointing at prior TZ
    LONG_TZ = "long_tz"
    TASK = "task"  # has substance but not huge
    PAY = "pay"
    OTHER = "other"


TASK_KEYWORDS = re.compile(
    r"(?i)(?:\bтз\b|техзадан|задач[ауие]|нужен|нужна|нужно|сделать|сделаем|"
    r"парсер|бот|утилита|софт|скрипт|сайт|веб|дрейнер|прокси|api|"
    r"разработ|автоматиз|интеграц|скачать|парс|wb|wildberries|вб|"
    r"telegram|телеграм|android|ios|редми|redmi|imei|"
    r"документац|uptime|запрос|прокс)",
)

SHORT_POINTER = re.compile(
    r"(?i)^(тз\s*вот|вот\s*тз|тз|вот|это|сюда|выше|смотри|глянь|там)[\s!.]*$",
)

BAD_GREETING_REPLY = re.compile(
    r"(?i)^(привет|здравствуйте|добрый\s+(день|вечер|утро)|hi|hello)"
    r"(?:,?\s*(слушаю|на\s+связи))?[\s!.]*$",
)

BAD_ASK_AGAIN = re.compile(
    r"(?i)(?:напишите?\s+что\s+нужно|напиши\s+что\s+нужно|"
    r"уточни\s+что\s+именно\s+нужно|"
    r"чем\s+могу\s+помочь\s*\?|что\s+нужно\s+сделать\s*\?|"
    r"слушаю[\s,.]*$|дайте\s+(тз|детал)|опишите\s+задачу)",
)

BAD_RE_ESTIMATE = re.compile(
    r"(?i)(?:цену\s+скажу\s+когда\s+соберу\s+оценк|"
    r"цену\s+скажу\s+когда\s+вс[её]\s+собер|"
    r"сейчас\s+оценю\s+и\s+вернусь)",
)

BAD_REPEAT_PITCH = re.compile(
    r"(?i)^делаем\b.+(?:под\s+ключ|настроим|запустим)",
)

REPLY_CTX_MARK = "[клиент отвечает на сообщение]"

# Openers that ignore what the client actually said. Never send these.
STOCK_OPENER = re.compile(
    r"(?i)^(?:"
    r"тз\s+вижу|"
    r"тз\s+принял(?:а)?|"
    r"ок,?\s*уч[её]л|"
    r"ок,?\s*докинул|"
    r"ок,?\s*задачу|"
    r"ок,?\s*по\s+\S+\s+задачу"
    r")"
)

EXACT_STOCK_REPLIES = {
    "уже собираю оценку, скоро напишу по цене и срокам",
    "напишите что нужно - сделаем под задачу",
    "уточни что именно нужно по задаче - цену скажу когда всё соберём",
    "привет, слушаю",
    "тз вижу, по объёму реально, сейчас оценю и вернусь с ценой и сроками",
    "ок, задачу разобрал, чуть уточню нюансы внутри и напишу цену",
    "тз принял, по такой нагрузке сделаем, цену скажу когда соберу оценку",
    "тз вижу, сейчас разберу и вернусь с оценкой",
    "ок, задачу по цитате вижу, оценю и напишу",
}

TZ_ACK_REPLIES = [
    "тз вижу, по объёму реально, сейчас оценю и вернусь с ценой и сроками",
    "ок, задачу разобрал, чуть уточню нюансы внутри и напишу цену",
    "тз принял, по такой нагрузке сделаем, цену скажу когда соберу оценку",
]

TZ_POINTER_ACK = [
    "тз вижу, сейчас разберу и вернусь с оценкой",
    "ок, задачу по цитате вижу, оценю и напишу",
]


def client_body(content: str) -> str:
    """Strip reply-enrichment wrapper to get what the client actually typed."""
    t = (content or "").strip()
    if REPLY_CTX_MARK in t and "[его ответ]:" in t:
        return t.split("[его ответ]:", 1)[-1].strip()
    return t


def has_reply_context(content: str) -> bool:
    return REPLY_CTX_MARK in (content or "")


def has_task_substance(content: str) -> bool:
    t = (content or "").strip()
    if not t:
        return False
    body = client_body(t)
    if has_reply_context(t) and len(t) > 60:
        return True
    if len(body) >= 80:
        return True
    if TASK_KEYWORDS.search(body) and len(body) >= 25:
        return True
    if body.count("\n") >= 2 and len(body) >= 40:
        return True
    return False


def is_compact_spec(content: str) -> bool:
    """A short brief with a product and a constraint, even if it ends with a price question."""
    body = client_body(content).strip()
    if not body or not TASK_KEYWORDS.search(body):
        return False
    if re.search(r"(?i)не\s+про\s+нов", body):
        return False
    if len(re.findall(r"\d+", body)) >= 1 and len(body) >= 50:
        return True
    if body.count(",") >= 2 and len(body) >= 50 and re.search(
        r"(?i)нужен|нужна|нужно|парсер|бот|сайт", body
    ):
        return True
    return False


def is_short_question(content: str) -> bool:
    """A short question is not a new brief, even if it mentions the word «тз»."""
    body = client_body(content).strip()
    if not body or len(body) >= 180 or body.count("\n") >= 3:
        return False
    if is_compact_spec(body):
        return False
    if re.search(r"(?i)не\s+про\s+нов", body):
        return True
    if body.endswith("?"):
        return True
    return bool(re.match(r"(?i)^(?:а\s+|можно\s+|есть\s+ли\s+|вы\s+)", body))


def should_fold_into_brief(content: str) -> bool:
    """True only when this message is more task scope, not a question or a side note.

    Clarifications («токены не в объёме») and questions («правки после сдачи?»)
    must not be glued onto the stored TZ. That glue later became the client offer.
    """
    from app.services.quick_replies import is_deal_process_question, is_price_request

    if is_short_question(content) or is_price_request(content) or is_deal_process_question(content):
        return False
    return has_task_substance(content)


def merge_task_summary(existing: str, incoming: str, last_message: str) -> str:
    """Keep the original brief unless the new message actually extends the scope."""
    base = (existing or "").strip()
    proposed = (incoming or "").strip()
    last = client_body(last_message).strip()
    if not should_fold_into_brief(last_message):
        return base[:2000]
    if proposed and (not base or base in proposed or len(proposed) >= len(base)):
        return proposed[:2000]
    if base and last and last not in base:
        return f"{base}\n{last}".strip()[:2000]
    return (base or proposed or last)[:2000]


_BAD_PITCH = re.compile(
    r"(?i)(?:привет|нашел\s+твой\s+контакт|подскажи,\s*такая|"
    r"^делаем\s+(?:нужен|нужна|нужно|привет)|тз\s+вижу|ок,\s*уч)"
)


_ANCHORS = (
    (r"парсер|wildberries|\bвб\b|\bwb\b", "парсер"),
    (r"прокси", "прокси"),
    (r"документ", "дока"),
    (r"рассыл", "рассылка"),
    (r"\bбот\b", "бот"),
    (r"токен", "токены"),
    (r"uptime|аптайм", "uptime"),
    (r"исходник|репозитор", "исходники"),
    (r"правк", "правки"),
)


def brief_anchors(content: str) -> list[str]:
    """Concrete details from the client text a reply should actually use."""
    body = client_body(content).lower()
    found: list[str] = []
    skip_parser = bool(re.search(r"без\s+парсер", body))
    for pattern, label in _ANCHORS:
        if skip_parser and label == "парсер":
            continue
        if re.search(pattern, body) and label not in found:
            found.append(label)
    for number in re.findall(r"\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+)?", body):
        token = re.sub(r"\s+", "", number)
        if token and token not in found:
            found.append(token)
        if len(found) >= 6:
            break
    return found


def reply_tracks_brief(reply: str, content: str) -> bool:
    """A substantial brief needs at least one of its own details in the answer."""
    if not has_task_substance(content):
        return True
    anchors = brief_anchors(content)
    if not anchors:
        return True
    low = (reply or "").lower()
    return any(anchor.lower() in low for anchor in anchors)


def usable_client_pitch(pitch: str) -> str:
    """Drop pitches that are a raw paste of the client's message."""
    text = re.sub(r"\s+", " ", (pitch or "").strip())
    if len(text) < 16 or _BAD_PITCH.search(text):
        return ""
    return text[:1000]


def is_short_pointer(content: str) -> bool:
    body = client_body(content)
    if has_reply_context(content) and len(body) <= 40:
        return True
    return bool(SHORT_POINTER.match(body.strip()))


def classify_message(content: str) -> MsgKind:
    from app.services.humanizer import is_greeting_only
    from app.services.quick_replies import is_escrow_pay_intent, is_ready_to_pay

    raw = content or ""
    body = client_body(raw)

    if is_ready_to_pay(body) or is_escrow_pay_intent(body):
        return MsgKind.PAY
    if is_short_pointer(raw):
        return MsgKind.SHORT_POINTER
    if has_task_substance(raw):
        if len(body) >= 80 or body.count("\n") >= 2:
            return MsgKind.LONG_TZ
        return MsgKind.TASK
    if is_greeting_only(body) and not has_reply_context(raw):
        return MsgKind.GREETING
    return MsgKind.OTHER


def is_stock_reply(reply: str) -> bool:
    """True for canned acks that do not track the client's last message."""
    t = re.sub(r"\s+", " ", (reply or "").strip()).strip(" .,!")
    if not t:
        return False
    if t.lower() in EXACT_STOCK_REPLIES:
        return True
    if STOCK_OPENER.match(t):
        return True
    return False


def looks_like_bad_reply(reply: str, *, has_tz: bool, price_already: bool = False) -> bool:
    t = (reply or "").strip()
    if not t:
        return True
    if is_stock_reply(t):
        return True
    if BAD_GREETING_REPLY.match(t):
        return True
    if has_tz and BAD_ASK_AGAIN.search(t):
        return True
    if has_tz and len(t) < 12:
        return True
    if price_already and BAD_RE_ESTIMATE.search(t):
        return True
    if price_already and BAD_REPEAT_PITCH.search(t):
        return True
    return False


def ideal_tz_ack(*, pointer: bool = False, content: str = "") -> str:
    """Ack that optionally nods at the product type from TZ text."""
    lower = (content or "").lower()
    hint = ""
    if any(w in lower for w in ("парсер", "wildberries", "вб", "wb")):
        hint = "парсер"
    elif any(w in lower for w in ("дрейнер", "drainer", "tron", "trc20")):
        hint = "дрейнер"
    elif any(w in lower for w in ("бот", "telegram", "телеграм")):
        hint = "бота"
    elif any(w in lower for w in ("утилита", "imei", "редми", "android")):
        hint = "утилиту"
    elif any(w in lower for w in ("сайт", "веб", "web")):
        hint = "веб"

    if hint:
        variants = [
            f"тз вижу, {hint} под ваши условия сделаем, сейчас оценю и вернусь с ценой",
            f"ок, по {hint} задачу разобрал, цену скажу когда соберу оценку",
            f"тз принял, {hint} реально, чуть разложу внутри и напишу по цене и срокам",
        ]
        return random.choice(variants)
    if pointer:
        return random.choice(TZ_POINTER_ACK)
    return random.choice(TZ_ACK_REPLIES)


def quality_gate_reply(
    reply: str,
    *,
    content: str,
    has_tz_on_file: bool,
    kind: MsgKind | None = None,
    price_already: bool = False,
) -> str:
    """Drop stock acks so the caller can generate a reply that matches the message.

    After a price is already on the deal, a re-pitch becomes the deal-process answer.
    Otherwise a bad reply becomes empty: never substitute «тз вижу» / «ок, учёл».
    """
    kind = kind or classify_message(content)
    has_tz = has_tz_on_file or kind in (MsgKind.LONG_TZ, MsgKind.TASK, MsgKind.SHORT_POINTER)
    text = (reply or "").strip()
    if is_stock_reply(text):
        if price_already:
            from app.services.quick_replies import deal_process_reply

            return deal_process_reply(has_quote=True)
        return ""
    if not looks_like_bad_reply(text, has_tz=has_tz, price_already=price_already):
        return text
    if price_already:
        from app.services.quick_replies import deal_process_reply

        return deal_process_reply(has_quote=True)
    if has_tz or kind in (MsgKind.LONG_TZ, MsgKind.TASK, MsgKind.SHORT_POINTER, MsgKind.OTHER):
        return ""
    return text


def last_long_user_text(history_msgs: list, *, min_len: int = 80) -> str | None:
    """Find latest substantial client message for short-pointer without reply-to."""
    from app.db.models import MessageRole

    for msg in reversed(history_msgs or []):
        if getattr(msg, "role", None) != MessageRole.USER:
            continue
        text = (getattr(msg, "content", None) or "").strip()
        body = client_body(text)
        if len(body) >= min_len or has_task_substance(text):
            return text
    return None


def enrich_short_pointer_from_history(content: str, history_msgs: list) -> str:
    """If client says «тз вот» without reply-to, attach last long TZ from history."""
    if has_reply_context(content):
        return content
    if not is_short_pointer(content):
        return content
    prior = last_long_user_text(history_msgs)
    if not prior:
        return content
    body = client_body(content)
    quoted = client_body(prior)[:4000]
    return (
        f"{REPLY_CTX_MARK}:\n{quoted}\n\n"
        f"[его ответ]:\n{body}"
    )
