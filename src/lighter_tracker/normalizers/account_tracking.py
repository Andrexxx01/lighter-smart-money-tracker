"""Normalisasi defensif respons SDK Lighter untuk pemantauan read-only.

Tidak mengasumsikan bahwa sign=1 berarti LONG. Simpan nilai mentahnya.
Semua angka finansial menggunakan Decimal, bukan float.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Any

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def field(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def address_of(value: object) -> str:
    addr = str(value).strip()
    if not ADDRESS_RE.fullmatch(addr):
        raise ValueError(f"Alamat L1 tidak valid: {value!r}")
    return addr.lower()


def integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} bukan integer valid: {value!r}")
    try:
        n = int(str(value))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} bukan integer valid: {value!r}") from exc
    if str(value).strip() != str(n):
        raise ValueError(f"{name} bukan integer kanonis: {value!r}")
    if n < minimum:
        raise ValueError(f"{name} harus >= {minimum}")
    return n


def dec(value: object, name: str, *, optional: bool = False) -> Decimal | None:
    if optional and (value is None or value == ""):
        return None
    if value is None or isinstance(value, bool):
        raise ValueError(f"{name} kosong/tidak valid")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} bukan angka valid: {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"{name} tidak boleh NaN/Infinity")
    return result


@dataclass(frozen=True)
class AccountIdentity:
    l1_address: str
    account_index: int


@dataclass(frozen=True)
class PositionObservation:
    market_id: int
    symbol: str
    raw_sign: int
    quantity: Decimal
    avg_entry_price: Decimal
    position_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    liquidation_price: Decimal | None
    margin_mode: int | None
    allocated_margin: Decimal | None


@dataclass(frozen=True)
class AccountObservation:
    account_index: int
    l1_address: str
    collateral: Decimal
    available_balance: Decimal
    total_asset_value: Decimal | None
    positions: tuple[PositionObservation, ...]
    source_transaction_time: str | None = None


def normalize_sub_accounts(response: Any, requested_address: str) -> tuple[AccountIdentity, ...]:
    address = address_of(requested_address)
    rows = field(response, "sub_accounts")
    if rows is None:
        raise ValueError("Respons tidak memiliki sub_accounts; jangan anggap sebagai daftar kosong")
    result: list[AccountIdentity] = []
    seen: set[int] = set()
    for row in rows:
        row_addr = address_of(field(row, "l1_address"))
        if row_addr != address:
            raise ValueError("Respons sub-account tidak cocok dengan alamat yang diminta")
        idx = integer(field(row, "index"), "account.index")
        if idx in seen:
            raise ValueError(f"Account index duplikat dalam halaman: {idx}")
        seen.add(idx)
        result.append(AccountIdentity(row_addr, idx))
    return tuple(result)


def normalize_detailed_account(response: Any, requested_index: int) -> AccountObservation:
    requested_index = integer(requested_index, "requested_index")
    accounts = field(response, "accounts")
    if accounts is None:
        raise ValueError("Respons tidak memiliki accounts")
    matches = [a for a in accounts if field(a, "index", field(a, "account_index")) is not None
               and integer(field(a, "index", field(a, "account_index")), "account.index") == requested_index]
    if len(matches) != 1:
        raise ValueError(f"Harus ada tepat satu account index={requested_index}; ditemukan {len(matches)}")
    account = matches[0]
    address = address_of(field(account, "l1_address"))
    raw_positions = field(account, "positions")
    if raw_positions is None:
        raise ValueError("Field positions hilang; snapshot tidak boleh dianggap kosong")
    positions: list[PositionObservation] = []
    markets: set[int] = set()
    for p in raw_positions:
        market_id = integer(field(p, "market_id"), "market_id")
        if market_id in markets:
            raise ValueError(f"Market ID duplikat: {market_id}")
        markets.add(market_id)
        qty = dec(field(p, "position"), "position")
        assert qty is not None
        if qty == 0:
            continue  # market kosong tidak dicatat sebagai posisi terbuka
        symbol = str(field(p, "symbol") or "").strip()
        if not symbol:
            raise ValueError("Symbol posisi tidak boleh kosong")
        sign = integer(field(p, "sign"), "sign", minimum=-2**31)
        margin_mode_raw = field(p, "margin_mode")
        margin_mode = (integer(margin_mode_raw, "margin_mode")
                       if margin_mode_raw is not None else None)
        positions.append(PositionObservation(
            market_id=market_id, symbol=symbol, raw_sign=sign, quantity=qty,
            avg_entry_price=dec(field(p, "avg_entry_price"), "avg_entry_price"),
            position_value=dec(field(p, "position_value"), "position_value"),
            unrealized_pnl=dec(field(p, "unrealized_pnl"), "unrealized_pnl"),
            realized_pnl=dec(field(p, "realized_pnl"), "realized_pnl"),
            liquidation_price=dec(field(p, "liquidation_price"), "liquidation_price", optional=True),
            margin_mode=margin_mode,
            allocated_margin=dec(field(p, "allocated_margin"), "allocated_margin", optional=True),
        ))
    return AccountObservation(
        account_index=requested_index,
        l1_address=address,
        collateral=dec(field(account, "collateral"), "collateral"),
        available_balance=dec(field(account, "available_balance"), "available_balance"),
        total_asset_value=dec(field(account, "total_asset_value"), "total_asset_value", optional=True),
        positions=tuple(positions),
        source_transaction_time=(str(field(account, "transaction_time"))
                                 if field(account, "transaction_time") is not None else None),
    )
