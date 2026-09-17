"""Download and interpret Telegram media for the sales agent."""
from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path

from telegram import Bot, Message

from app.config import get_settings
from app.services.llm import generate_text

logger = logging.getLogger(__name__)
settings = get_settings()


async def process_incoming_media(bot: Bot, message: Message) -> tuple[str, str]:
    """Returns (text_content, media_type)."""
    if message.sticker:
        emoji = getattr(message.sticker, "emoji", None) or ""
        return (f"[стикер] {emoji}".strip(), "sticker")
    if message.voice or message.audio:
        return await _transcribe_voice(bot, message), "voice"
    if message.photo:
        return await _describe_photo(bot, message), "photo"
    if message.document:
        return await _read_document(bot, message), "document"
    if message.video_note:
        return await _transcribe_voice(bot, message, video_note=True), "voice"
    return message.text or message.caption or "", "text"


async def _download(bot: Bot, message: Message) -> bytes:
    if message.voice:
        f = message.voice
    elif message.audio:
        f = message.audio
    elif message.document:
        f = message.document
    elif message.photo:
        f = message.photo[-1]
    elif message.video_note:
        f = message.video_note
    else:
        return b""
    tg_file = await bot.get_file(f.file_id)
    buf = io.BytesIO()
    await tg_file.download_to_memory(out=buf)
    return buf.getvalue()


async def _transcribe_voice(bot: Bot, message: Message, video_note: bool = False) -> str:
    data = await _download(bot, message)
    if not data:
        return "[голосовое сообщение — не удалось скачать]"

  # Gemini multimodal
    if settings.google_api_key:
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.google_api_key)
            model = genai.GenerativeModel(settings.gemini_model)
            suffix = ".ogg" if not video_note else ".mp4"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(data)
                path = tmp.name
            mime = "audio/ogg" if not video_note else "video/mp4"
            uploaded = genai.upload_file(path, mime_type=mime)
            resp = await model.generate_content_async(
                ["Транскрибируй это голосовое сообщение на русском, только текст без пояснений.", uploaded]
            )
            Path(path).unlink(missing_ok=True)
            text = (resp.text or "").strip()
            if text:
                return f"[голосовое]: {text}"
        except Exception as e:
            logger.warning("voice transcribe: %s", e)

    if settings.openai_api_key:
        try:
            from openai import AsyncOpenAI
            from app.services.providers import _openai_base_url

            kwargs: dict = {"api_key": settings.openai_api_key}
            base = _openai_base_url()
            if base:
                kwargs["base_url"] = base
            client = AsyncOpenAI(**kwargs)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                tmp.write(data)
                path = tmp.name
            with open(path, "rb") as audio:
                tr = await client.audio.transcriptions.create(model="whisper-1", file=audio)
            Path(path).unlink(missing_ok=True)
            return f"[голосовое]: {tr.text}"
        except Exception as e:
            logger.warning("whisper: %s", e)

    return "[голосовое сообщение — пришлите текстом или опишите задачу]"


async def _describe_photo(bot: Bot, message: Message) -> str:
    data = await _download(bot, message)
    caption = message.caption or ""
    if not data:
        return caption or "[фото]"

    if settings.google_api_key:
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.google_api_key)
            model = genai.GenerativeModel(settings.gemini_model)
            prompt = (
                "Опиши что на изображении для менеджера по разработке. "
                "Если это ТЗ, скрин, макет или схема — извлеки суть и текст. Кратко по-русски."
            )
            if caption:
                prompt += f"\nПодпись клиента: {caption}"
            resp = await model.generate_content_async(
                [
                    prompt,
                    {"mime_type": "image/jpeg", "data": data},
                ]
            )
            desc = (resp.text or "").strip()
            return f"[фото]: {desc}" + (f"\nподпись: {caption}" if caption else "")
        except Exception as e:
            logger.warning("photo vision: %s", e)

    return caption or "[фото — не удалось распознать, опишите текстом]"


async def _read_document(bot: Bot, message: Message) -> str:
    doc = message.document
    if not doc:
        return ""
    data = await _download(bot, message)
    name = doc.file_name or "file"
    suffix = Path(name).suffix.lower()

    try:
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages[:20])
            return f"[документ {name}]:\n{text[:4000]}"
        if suffix in (".docx",):
            from docx import Document

            d = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in d.paragraphs if p.text)
            return f"[документ {name}]:\n{text[:4000]}"
        if suffix in (".txt", ".md"):
            return f"[файл {name}]:\n{data.decode('utf-8', errors='ignore')[:4000]}"
    except Exception as e:
        logger.warning("doc read %s: %s", name, e)

    return f"[документ {name} — пришлите текстом или pdf/docx]"
