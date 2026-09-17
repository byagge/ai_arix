"""Payment message templates — {usdt-tron} etc."""
from __future__ import annotations

from sqlalchemy import select

from app.database import async_session
from app.db.bot_extensions import PaymentTemplate

# Telegram HTML: <b> <i> <u> <s> <code> <pre> <blockquote> <tg-spoiler> <a>
# Premium emoji вставляйте как есть — система их не трогает.
DEFAULT_TEMPLATES = [
    {
        "network_key": "usdt-tron",
        "label": "USDT · TRC-20 (Tron)",
        "wallet_address": "",
        "message_template": (
            "<b>Оплата USDT TRC-20</b>\n"
            "Сумма: <code>{amount}</code> USDT\n"
            "Адрес (нажмите, чтобы скопировать):\n"
            "<code>{address}</code>\n"
            "Сеть: <b>Tron · TRC-20</b>\n"
            "После перевода пришлите <i>txid</i>"
        ),
    },
    {
        "network_key": "usdt-bep20",
        "label": "USDT · BEP-20 (BSC)",
        "wallet_address": "",
        "message_template": (
            "<b>Оплата USDT BEP-20</b>\n"
            "Сумма: <code>{amount}</code> USDT\n"
            "Адрес:\n<code>{address}</code>\n"
            "Сеть: <b>BNB Smart Chain · BEP-20</b>\n"
            "После перевода пришлите txid"
        ),
    },
    {
        "network_key": "usdt-erc20",
        "label": "USDT · ERC-20 (Ethereum)",
        "wallet_address": "",
        "message_template": (
            "<b>Оплата USDT ERC-20</b>\n"
            "Сумма: <code>{amount}</code> USDT\n"
            "Адрес:\n<code>{address}</code>\n"
            "Сеть: <b>Ethereum · ERC-20</b>\n"
            "<i>Учитывайте комиссию газа</i>"
        ),
    },
    {
        "network_key": "usdt-sol",
        "label": "USDT · Solana",
        "wallet_address": "",
        "message_template": (
            "<b>Оплата USDT (Solana)</b>\n"
            "Сумма: <code>{amount}</code> USDT\n"
            "Адрес:\n<code>{address}</code>\n"
            "Сеть: <b>Solana</b>"
        ),
    },
    {
        "network_key": "usdt-ton",
        "label": "USDT · TON",
        "wallet_address": "",
        "message_template": (
            "<b>Оплата USDT (TON)</b>\n"
            "Сумма: <code>{amount}</code> USDT\n"
            "Адрес:\n<code>{address}</code>\n"
            "Сеть: <b>The Open Network</b>"
        ),
    },
    {
        "network_key": "ton",
        "label": "TON (native)",
        "wallet_address": "",
        "message_template": (
            "<b>Оплата TON</b>\n"
            "Сумма: <code>{amount}</code> TON\n"
            "Адрес:\n<code>{address}</code>"
        ),
    },
    {
        "network_key": "usdt-polygon",
        "label": "USDT · Polygon",
        "wallet_address": "",
        "message_template": (
            "<b>Оплата USDT (Polygon)</b>\n"
            "Сумма: <code>{amount}</code> USDT\n"
            "Адрес:\n<code>{address}</code>\n"
            "Сеть: <b>Polygon · PoS</b>"
        ),
    },
    {
        "network_key": "usdt-arbitrum",
        "label": "USDT · Arbitrum",
        "wallet_address": "",
        "message_template": (
            "<b>Оплата USDT (Arbitrum)</b>\n"
            "Сумма: <code>{amount}</code> USDT\n"
            "Адрес:\n<code>{address}</code>\n"
            "Сеть: <b>Arbitrum One</b>"
        ),
    },
    {
        "network_key": "usdt-optimism",
        "label": "USDT · Optimism",
        "wallet_address": "",
        "message_template": (
            "<b>Оплата USDT (Optimism)</b>\n"
            "Сумма: <code>{amount}</code> USDT\n"
            "Адрес:\n<code>{address}</code>\n"
            "Сеть: <b>Optimism</b>"
        ),
    },
    {
        "network_key": "usdt-avax",
        "label": "USDT · Avalanche C-Chain",
        "wallet_address": "",
        "message_template": (
            "<b>Оплата USDT (Avalanche)</b>\n"
            "Сумма: <code>{amount}</code> USDT\n"
            "Адрес:\n<code>{address}</code>\n"
            "Сеть: <b>Avalanche C-Chain</b>"
        ),
    },
]


async def seed_templates() -> None:
    async with async_session() as db:
        for tpl in DEFAULT_TEMPLATES:
            exists = await db.scalar(
                select(PaymentTemplate.id).where(
                    PaymentTemplate.network_key == tpl["network_key"]
                )
            )
            if exists:
                continue
            db.add(PaymentTemplate(**tpl))
        await db.commit()


async def get_template(network_key: str) -> PaymentTemplate | None:
    async with async_session() as db:
        result = await db.execute(
            select(PaymentTemplate).where(
                PaymentTemplate.network_key == network_key,
                PaymentTemplate.enabled.is_(True),
            )
        )
        return result.scalar_one_or_none()


async def render_payment_message(network_key: str, amount: float) -> str | None:
    tpl = await get_template(network_key)
    if not tpl:
        return None
    msg = tpl.message_template
    msg = msg.replace("{amount}", f"{amount:g}")
    msg = msg.replace("{address}", tpl.wallet_address)
    return msg


PLACEHOLDER_RE = __import__("re").compile(r"\{([a-z0-9-]+)\}")


async def expand_placeholders_in_text(text: str, amount: float = 0) -> str:
    """Replace {usdt-tron} and similar tokens in AI output."""
    out = text
    for match in PLACEHOLDER_RE.finditer(text):
        key = match.group(1)
        rendered = await render_payment_message(key, amount)
        if rendered:
            out = out.replace(f"{{{key}}}", rendered)
    return out
