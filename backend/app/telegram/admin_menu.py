"""Telegram admin panel — /start for admin with inline navigation."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.config import get_settings

settings = get_settings()

STATUS_LABELS = {
    "lead": "Лид",
    "quoting": "Обсуждение",
    "payment_pending": "Ждём оплату",
    "paid": "Оплачено",
    "in_progress": "На работе",
    "completed": "Выполнен",
    "paused": "Пауза",
    "lost": "Потерян",
}


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text, callback_data=cb) for text, cb in row] for row in rows]
    )


ADMIN_MENU = _kb(
    [
        [("📊 Статистика", "adm:stats"), ("💬 Диалоги", "adm:dialogs")],
        [("💰 Оплаты", "adm:payments"), ("📋 Гарант черновики", "adm:escrow")],
        [("⚙️ Настройки", "adm:settings"), ("🌐 Платформа", "adm:web")],
    ]
)


async def send_admin_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    text = (
        "🛠 *Arix Admin*\n\n"
        "Управление Business Bot, оплатами и клиентами.\n"
        "Выберите раздел:"
    )
    await msg.reply_text(text, reply_markup=ADMIN_MENU, parse_mode="Markdown")


async def on_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data:
        return
    user = update.effective_user
    if not user or not settings.telegram_admin_id or user.id != settings.telegram_admin_id:
        await q.answer("Нет доступа", show_alert=True)
        return

    data = q.data
    if data.startswith("adm:dlg:"):
        await _handle_dialog_action(q, data)
        return
    if data.startswith("adm:st:"):
        await _set_dialog_status(q, data)
        return
    if not data.startswith("adm:"):
        return

    await q.answer()
    action = data.split(":", 1)[1]

    from sqlalchemy import func, select

    from app.database import async_session
    from app.db.models import Dialog, Order, PaymentStatus

    async with async_session() as db:
        if action == "stats":
            total = await db.scalar(select(func.count(Dialog.id))) or 0
            active = await db.scalar(
                select(func.count(Dialog.id)).where(Dialog.work_status == "in_progress")
            ) or 0
            pending = await db.scalar(
                select(func.count(Dialog.id)).where(Dialog.work_status == "payment_pending")
            ) or 0
            paid = await db.scalar(
                select(func.count(Order.id)).where(Order.payment_status == PaymentStatus.CONFIRMED)
            ) or 0
            revenue = (
                await db.scalar(
                    select(func.coalesce(func.sum(Order.amount_usdt), 0.0)).where(
                        Order.payment_status == PaymentStatus.CONFIRMED
                    )
                )
                or 0.0
            )
            text = (
                f"📊 Статистика\n\n"
                f"Диалогов: {total}\n"
                f"На работе: {active}\n"
                f"Ждут оплату: {pending}\n"
                f"Оплачено заказов: {paid}\n"
                f"Выручка: {float(revenue):.2f} USDT"
            )
        elif action == "dialogs":
            rows = (
                await db.execute(
                    select(Dialog)
                    .order_by(Dialog.last_message_at.desc().nullslast())
                    .limit(8)
                )
            ).scalars().all()
            if not rows:
                text = "Диалогов пока нет"
                markup = ADMIN_MENU
            else:
                lines = ["💬 Последние диалоги (нажмите для статуса):\n"]
                kb_rows: list[list[tuple[str, str]]] = []
                for d in rows:
                    name = d.first_name or d.telegram_username or d.telegram_user_id
                    st = STATUS_LABELS.get(d.work_status or "lead", d.work_status)
                    lines.append(f"• {name} — {st}")
                    kb_rows.append([(f"✏️ {name[:20]}", f"adm:dlg:{d.id}")])
                kb_rows.append([("◀️ Назад", "adm:home")])
                text = "\n".join(lines)
                markup = _kb(kb_rows)
                await q.edit_message_text(text, reply_markup=markup)
                return
        elif action == "payments":
            orders = (
                await db.execute(
                    select(Order)
                    .where(Order.payment_status.in_([PaymentStatus.PENDING, PaymentStatus.CONFIRMING]))
                    .order_by(Order.created_at.desc())
                    .limit(10)
                )
            ).scalars().all()
            if not orders:
                text = "💰 Нет ожидающих оплат"
            else:
                lines = ["💰 Ожидают оплату:\n"]
                for o in orders:
                    net = (o.escrow_draft_notes or "usdt-tron").replace("network:", "").split("|")[0]
                    lines.append(
                        f"• #{o.id} — {o.amount_usdt} USDT ({net})\n  {o.wallet_address[:16]}…"
                    )
                text = "\n".join(lines)
        elif action == "escrow":
            from app.payments.escrow import list_escrow_drafts

            drafts = await list_escrow_drafts()
            if not drafts:
                text = "📋 Черновиков гаранта нет"
            else:
                text = "📋 Черновики гаранта:\n" + "\n".join(
                    f"• {d.get('draft_id')} — {d.get('amount_usdt')} USDT" for d in drafts[:5]
                )
        elif action == "settings":
            text = (
                "⚙️ Настройки\n\n"
                "Веб: http://localhost:3000/payments-admin\n"
                "Клиенты: http://localhost:3000/clients"
            )
        elif action == "web":
            text = "🌐 Платформа: http://localhost:3000/clients"
        elif action == "home":
            await q.edit_message_text(
                "🛠 Arix Admin\n\nВыберите раздел:", reply_markup=ADMIN_MENU
            )
            return
        else:
            text = "Неизвестная команда"
        await q.edit_message_text(text, reply_markup=ADMIN_MENU)


async def _handle_dialog_action(q, data: str) -> None:
    await q.answer()
    dialog_id = int(data.split(":")[-1])
    from sqlalchemy import select

    from app.database import async_session
    from app.db.models import Dialog

    async with async_session() as db:
        d = await db.get(Dialog, dialog_id)
        if not d:
            await q.edit_message_text("Диалог не найден", reply_markup=ADMIN_MENU)
            return
        name = d.first_name or d.telegram_username or d.telegram_user_id
        st = STATUS_LABELS.get(d.work_status or "lead", d.work_status)
        text = f"👤 {name}\nСтатус: {st}\n\nВыберите новый статус:"
        kb = _kb(
            [
                [("✅ Выполнен", f"adm:st:{dialog_id}:completed")],
                [("🔨 На работе", f"adm:st:{dialog_id}:in_progress")],
                [("💳 Ждём оплату", f"adm:st:{dialog_id}:payment_pending")],
                [("◀️ Назад", "adm:dialogs")],
            ]
        )
        await q.edit_message_text(text, reply_markup=kb)


async def _set_dialog_status(q, data: str) -> None:
    await q.answer("Статус обновлён")
    parts = data.split(":")
    dialog_id = int(parts[2])
    status = parts[3]

    from app.database import async_session
    from app.db.models import Dialog

    async with async_session() as db:
        d = await db.get(Dialog, dialog_id)
        if d:
            d.work_status = status
            if status == "completed":
                d.silent_until_completed = False
            await db.commit()

    label = STATUS_LABELS.get(status, status)
    await q.edit_message_text(f"✅ Статус изменён: {label}", reply_markup=ADMIN_MENU)
