"""Multi-chain payment detection via public APIs — no API keys required.

Supported networks:
  usdt-tron   — Tronscan public API
  usdt-bep20  — BSC Blockscout public API
  ton         — Toncenter public API (native TON)
  usdt-erc20  — Etherscan public API (rate-limited, no key for low volume)

Falls back to TronGrid when TRON_API_KEY is set for higher rate limits.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

USDT_TRON_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDT_BEP20_CONTRACT = "0x55d398326f99059fF775485246999027B3197955"
USDT_ERC20_CONTRACT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


async def check_incoming(
    network_key: str,
    address: str,
    min_amount: float,
    since: datetime | None = None,
) -> dict[str, Any]:
    """Return {status, tx_hash, amount, confirmations} or {status: pending}."""
    since = since or datetime(2000, 1, 1, tzinfo=timezone.utc)
    key = network_key.lower().strip()

    try:
        if key in ("usdt-tron", "tron", "trc20"):
            return await _check_tron_usdt(address, min_amount, since)
        if key in ("usdt-bep20", "bep20", "bsc"):
            return await _check_bep20_usdt(address, min_amount, since)
        if key in ("ton",):
            return await _check_ton_native(address, min_amount, since)
        if key in ("usdt-erc20", "erc20", "eth"):
            return await _check_erc20_usdt(address, min_amount, since)
        return {"status": "unsupported_network", "network": network_key}
    except Exception as e:
        logger.warning("check_incoming %s %s: %s", network_key, address[:12], e)
        return {"status": "error", "error": str(e)[:200]}


async def _check_tron_usdt(address: str, min_amount: float, since: datetime) -> dict:
    since_ms = int(since.timestamp() * 1000)
    transfers: list[dict] = []

    # 1) Tronscan — no API key
    url = "https://apilist.tronscanapi.com/api/token_trc20/transfers"
    params = {
        "relatedAddress": address,
        "contract": USDT_TRON_CONTRACT,
        "limit": 30,
        "start": 0,
        "direction": 2,  # incoming
    }
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(url, params=params)
        if r.status_code == 200:
            data = r.json()
            for item in data.get("token_transfers") or data.get("data") or []:
                transfers.append(item)

    # 2) TronGrid fallback (optional key)
    if not transfers:
        headers = {}
        if settings.tron_api_key:
            headers["TRON-PRO-API-KEY"] = settings.tron_api_key
        url2 = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"
        params2 = {"limit": 30, "contract_address": USDT_TRON_CONTRACT}
        async with httpx.AsyncClient(timeout=25) as client:
            r2 = await client.get(url2, params=params2, headers=headers)
            if r2.status_code == 200:
                for item in r2.json().get("data", []):
                    transfers.append(item)

    for t in transfers:
        to_addr = (t.get("to_address") or t.get("to") or "").strip()
        if to_addr and to_addr != address and to_addr.lower() != address.lower():
            # Tronscan uses same field names
            if t.get("to_address") and t["to_address"] != address:
                continue
        ts = t.get("block_ts") or t.get("block_timestamp") or 0
        if ts and ts < since_ms:
            continue
        raw = t.get("quant") or t.get("value") or 0
        try:
            amount = int(raw) / 1_000_000
        except (TypeError, ValueError):
            amount = float(raw or 0)
        if amount >= min_amount * 0.99:
            return {
                "status": "confirmed",
                "tx_hash": t.get("transaction_id") or t.get("transactionHash"),
                "amount": amount,
                "network": "usdt-tron",
                "confirmations": 1,
            }
    return {"status": "pending"}


async def _check_bep20_usdt(address: str, min_amount: float, since: datetime) -> dict:
    since_ts = since.isoformat()
    url = f"https://bsc.blockscout.com/api/v2/addresses/{address}/token-transfers"
    params = {"type": "ERC-20"}
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            return {"status": "pending"}
        items = r.json().get("items") or []

    for item in items:
        token = item.get("token") or {}
        sym = (token.get("symbol") or "").upper()
        if sym != "USDT" and USDT_BEP20_CONTRACT.lower() not in (token.get("address") or "").lower():
            continue
        to_obj = item.get("to") or {}
        to_hash = to_obj.get("hash") if isinstance(to_obj, dict) else to_obj
        if to_hash and to_hash.lower() != address.lower():
            continue
        ts = item.get("timestamp") or ""
        if ts and ts < since_ts:
            continue
        try:
            decimals = int(token.get("decimals") or 18)
            raw = int(item.get("total") or item.get("value") or 0)
            amount = raw / (10**decimals)
        except (TypeError, ValueError):
            amount = float(item.get("value") or 0)
        if amount >= min_amount * 0.99:
            return {
                "status": "confirmed",
                "tx_hash": item.get("tx_hash"),
                "amount": amount,
                "network": "usdt-bep20",
                "confirmations": 1,
            }
    return {"status": "pending"}


async def _check_ton_native(address: str, min_amount: float, since: datetime) -> dict:
    url = "https://toncenter.com/api/v2/getTransactions"
    params = {"address": address, "limit": 20, "archival": "true"}
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            return {"status": "pending"}
        result = r.json().get("result") or []

    since_ts = int(since.timestamp())
    for tx in result:
        utime = tx.get("utime") or 0
        if utime < since_ts:
            continue
        in_msg = tx.get("in_msg") or {}
        value = int(in_msg.get("value") or 0)
        amount = value / 1_000_000_000  # nanoton
        if amount >= min_amount * 0.99:
            return {
                "status": "confirmed",
                "tx_hash": tx.get("transaction_id", {}).get("hash") if isinstance(tx.get("transaction_id"), dict) else str(tx.get("transaction_id", "")),
                "amount": amount,
                "network": "ton",
                "confirmations": 1,
            }
    return {"status": "pending"}


async def _check_erc20_usdt(address: str, min_amount: float, since: datetime) -> dict:
    # Etherscan public — no key, 5 req/s limit
    url = "https://api.etherscan.io/api"
    params = {
        "module": "account",
        "action": "tokentx",
        "contractaddress": USDT_ERC20_CONTRACT,
        "address": address,
        "page": 1,
        "offset": 20,
        "sort": "desc",
    }
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(url, params=params)
        if r.status_code != 200:
            return {"status": "pending"}
        data = r.json()
        if data.get("status") != "1":
            return {"status": "pending"}
        txs = data.get("result") or []

    since_ts = int(since.timestamp())
    for tx in txs:
        if tx.get("to", "").lower() != address.lower():
            continue
        ts = int(tx.get("timeStamp") or 0)
        if ts < since_ts:
            continue
        amount = int(tx.get("value") or 0) / 1_000_000
        if amount >= min_amount * 0.99:
            return {
                "status": "confirmed",
                "tx_hash": tx.get("hash"),
                "amount": amount,
                "network": "usdt-erc20",
                "confirmations": int(tx.get("confirmations") or 1),
            }
    return {"status": "pending"}
