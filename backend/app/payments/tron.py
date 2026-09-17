import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import qrcode
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Order, PaymentMethod, PaymentStatus

settings = get_settings()
QR_DIR = Path("uploads/qr")
QR_DIR.mkdir(parents=True, exist_ok=True)

USDT_DECIMALS = 6


def _get_sync_session() -> Session:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(settings.database_url_sync)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def generate_tron_address(index: int) -> str:
    """Generate deterministic address from master mnemonic (HD wallet simulation)."""
    if settings.tron_master_mnemonic:
        try:
            from tronpy.keys import PrivateKey

            seed = f"{settings.tron_master_mnemonic}:{index}".encode()
            import hashlib

            pk_bytes = hashlib.sha256(seed).digest()
            pk = PrivateKey(pk_bytes)
            return pk.public_key.to_base58check_address()
        except Exception:
            pass
    return f"T{'X' * 33}{index:04d}"


def generate_qr(address: str, amount: float) -> str:
    uri = f"tron:{address}?amount={amount}&token=USDT"
    img = qrcode.make(uri)
    path = QR_DIR / f"{uuid.uuid4().hex}.png"
    img.save(str(path))
    return str(path)


async def create_payment_order(
    dialog_id: int,
    amount_usdt: float = 0,
    description: str = "Заказ",
) -> dict:
    db = _get_sync_session()
    try:
        last = db.execute(
            select(Order.wallet_index).where(Order.wallet_index.isnot(None)).order_by(Order.wallet_index.desc()).limit(1)
        ).scalar_one_or_none()
        index = (last or 0) + 1
        address = generate_tron_address(index)
        amount = amount_usdt or 100.0
        qr_path = generate_qr(address, amount)

        order = Order(
            dialog_id=dialog_id,
            amount_usdt=amount,
            description=description,
            payment_method=PaymentMethod.DIRECT_USDT,
            payment_status=PaymentStatus.PENDING,
            wallet_address=address,
            wallet_index=index,
            qr_code_path=qr_path,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return {
            "order_id": order.id,
            "wallet_address": address,
            "amount_usdt": amount,
            "qr_code_path": qr_path,
        }
    finally:
        db.close()


async def check_tron_payment(order_id: int) -> dict:
    db = _get_sync_session()
    try:
        order = db.get(Order, order_id)
        if not order or not order.wallet_address:
            return {"status": "not_found"}

        if order.payment_status == PaymentStatus.CONFIRMED:
            return {"status": "confirmed", "tx_hash": order.tx_hash}

        tx = await _fetch_usdt_transactions(order.wallet_address)
        for t in tx:
            amount = t.get("amount_usdt", 0)
            if amount >= order.amount_usdt * 0.99:
                confirmations = t.get("confirmations", 0)
                if confirmations >= settings.tron_confirmations:
                    order.payment_status = PaymentStatus.CONFIRMED
                    order.tx_hash = t.get("tx_hash")
                    order.paid_at = datetime.now(timezone.utc)
                    db.commit()
                    return {"status": "confirmed", "tx_hash": order.tx_hash}
                order.payment_status = PaymentStatus.CONFIRMING
                db.commit()
                return {"status": "confirming", "confirmations": confirmations}

        return {"status": order.payment_status.value}
    finally:
        db.close()


async def _fetch_usdt_transactions(address: str) -> list[dict]:
    if not settings.tron_api_key:
        return []
    url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"
    params = {"limit": 20, "contract_address": settings.usdt_contract}
    headers = {"TRON-PRO-API-KEY": settings.tron_api_key}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for item in data.get("data", []):
            if item.get("to") != address:
                continue
            value = int(item.get("value", 0)) / (10 ** USDT_DECIMALS)
            results.append({
                "tx_hash": item.get("transaction_id"),
                "amount_usdt": value,
                "confirmations": item.get("block_timestamp", 0),
            })
        return results


async def monitor_pending_orders() -> int:
    db = _get_sync_session()
    confirmed = 0
    try:
        orders = db.execute(
            select(Order).where(
                Order.payment_status.in_([PaymentStatus.PENDING, PaymentStatus.CONFIRMING]),
                Order.payment_method == PaymentMethod.DIRECT_USDT,
            )
        ).scalars().all()
        for order in orders:
            prev = order.payment_status
            result = await check_tron_payment(order.id)
            if result.get("status") == "confirmed" and prev != PaymentStatus.CONFIRMED:
                confirmed += 1
                await _notify_payment_received(order.dialog_id, order.id)
        return confirmed
    finally:
        db.close()


async def _notify_payment_received(dialog_id: int, order_id: int) -> None:
    from app.database import async_session
    from app.db.models import Dialog, Message, MessageRole
    from app.services.dialog_service import on_payment_confirmed, resolve_chat_id
    from app.telegram.client import send_telegram_message

    text = "Приняли деньги. Начинаем работу."
    async with async_session() as db:
        await on_payment_confirmed(db, dialog_id)
        dialog = await db.get(Dialog, dialog_id)
        db.add(
            Message(
                dialog_id=dialog_id,
                role=MessageRole.ASSISTANT,
                content=text,
                agent_name="payment",
            )
        )
        await db.commit()
        if dialog:
            try:
                await send_telegram_message(
                    resolve_chat_id(dialog),
                    text,
                    business_connection_id=dialog.business_connection_id,
                )
            except Exception:
                pass
            from app.telegram.client import send_admin_notification

            await send_admin_notification(
                f"Оплата подтверждена\norder #{order_id}\ndialog #{dialog_id}"
            )
