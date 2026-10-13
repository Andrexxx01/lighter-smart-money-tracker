"""Tabel tambahan untuk mapping account dan snapshot posisi. Tidak mengubah tabel sesi 4."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
from uuid import uuid4

from lighter_tracker.normalizers.account_tracking import (
    AccountIdentity, AccountObservation, PositionObservation, address_of, integer,
)

DEFAULT_DB_PATH = Path("data/lighter_tracker.sqlite3")


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _utc(value: datetime | None) -> str:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp harus timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def init_tracking_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS account_discovery_runs (
                    run_id TEXT PRIMARY KEY,
                    l1_address TEXT NOT NULL,
                    fetched_at_utc TEXT NOT NULL,
                    account_count INTEGER NOT NULL CHECK (account_count >= 0)
                );
                CREATE TABLE IF NOT EXISTS discovered_accounts (
                    run_id TEXT NOT NULL REFERENCES account_discovery_runs(run_id)
                        ON DELETE CASCADE,
                    account_index INTEGER NOT NULL CHECK (account_index >= 0),
                    l1_address TEXT NOT NULL,
                    PRIMARY KEY (run_id, account_index)
                );
                CREATE INDEX IF NOT EXISTS idx_discovered_accounts_address
                    ON discovered_accounts(l1_address, account_index);
                CREATE TABLE IF NOT EXISTS account_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    fetched_at_utc TEXT NOT NULL,
                    account_index INTEGER NOT NULL CHECK (account_index >= 0),
                    l1_address TEXT NOT NULL,
                    collateral TEXT NOT NULL,
                    available_balance TEXT NOT NULL,
                    total_asset_value TEXT,
                    source_transaction_time TEXT,
                    position_count INTEGER NOT NULL CHECK (position_count >= 0)
                );
                CREATE INDEX IF NOT EXISTS idx_account_snapshots_history
                    ON account_snapshots(account_index, fetched_at_utc DESC);
                CREATE TABLE IF NOT EXISTS position_snapshots (
                    snapshot_id TEXT NOT NULL REFERENCES account_snapshots(snapshot_id)
                        ON DELETE CASCADE,
                    market_id INTEGER NOT NULL CHECK (market_id >= 0),
                    symbol TEXT NOT NULL,
                    raw_sign INTEGER NOT NULL,
                    quantity TEXT NOT NULL,
                    avg_entry_price TEXT NOT NULL,
                    position_value TEXT NOT NULL,
                    unrealized_pnl TEXT NOT NULL,
                    realized_pnl TEXT NOT NULL,
                    liquidation_price TEXT,
                    margin_mode INTEGER,
                    allocated_margin TEXT,
                    PRIMARY KEY (snapshot_id, market_id)
                );
            """)


def save_discovery(
    l1_address: str,
    accounts: tuple[AccountIdentity, ...] | list[AccountIdentity],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    fetched_at: datetime | None = None,
) -> str:
    addr = address_of(l1_address)
    accounts = tuple(accounts)
    seen: set[int] = set()
    rows: list[tuple[int, str]] = []
    for a in accounts:
        if address_of(a.l1_address) != addr:
            raise ValueError("Account milik alamat lain")
        idx = integer(a.account_index, "account_index")
        if idx in seen:
            raise ValueError("Account index duplikat")
        seen.add(idx)
        rows.append((idx, addr))
    timestamp = _utc(fetched_at)
    run_id = uuid4().hex
    init_tracking_db(db_path)
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute("INSERT INTO account_discovery_runs VALUES (?, ?, ?, ?)",
                         (run_id, addr, timestamp, len(rows)))
            conn.executemany("INSERT INTO discovered_accounts VALUES (?, ?, ?)",
                             [(run_id, idx, address) for idx, address in rows])
    return run_id


def _as_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def save_account_snapshot(
    observation: AccountObservation,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    fetched_at: datetime | None = None,
) -> str:
    idx = integer(observation.account_index, "account_index")
    address = address_of(observation.l1_address)
    timestamp = _utc(fetched_at)
    positions = tuple(observation.positions)
    ids = [p.market_id for p in positions]
    if len(ids) != len(set(ids)):
        raise ValueError("Market ID duplikat dalam snapshot")
    # Input normally comes from strict normalizer; validate monetary values again.
    numbers = [observation.collateral, observation.available_balance, observation.total_asset_value]
    for p in positions:
        numbers.extend((p.quantity, p.avg_entry_price, p.position_value,
                        p.unrealized_pnl, p.realized_pnl, p.liquidation_price,
                        p.allocated_margin))
    if any(value is not None and (not isinstance(value, Decimal) or not value.is_finite())
           for value in numbers):
        raise ValueError("Angka snapshot harus Decimal finite")
    if any(p.quantity == 0 or p.market_id < 0 or not p.symbol.strip() for p in positions):
        raise ValueError("Hanya posisi aktif dengan market_id dan symbol valid")
    snapshot_id = uuid4().hex
    init_tracking_db(db_path)
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute("""INSERT INTO account_snapshots
                (snapshot_id, fetched_at_utc, account_index, l1_address, collateral,
                 available_balance, total_asset_value, source_transaction_time, position_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (snapshot_id, timestamp, idx, address, _as_text(observation.collateral),
                 _as_text(observation.available_balance), _as_text(observation.total_asset_value),
                 observation.source_transaction_time, len(positions)))
            conn.executemany("""INSERT INTO position_snapshots
                (snapshot_id, market_id, symbol, raw_sign, quantity, avg_entry_price,
                 position_value, unrealized_pnl, realized_pnl, liquidation_price,
                 margin_mode, allocated_margin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(snapshot_id, p.market_id, p.symbol, p.raw_sign, _as_text(p.quantity),
                  _as_text(p.avg_entry_price), _as_text(p.position_value),
                  _as_text(p.unrealized_pnl), _as_text(p.realized_pnl),
                  _as_text(p.liquidation_price), p.margin_mode, _as_text(p.allocated_margin))
                 for p in positions])
    return snapshot_id


@dataclass(frozen=True)
class StoredAccountSnapshot:
    snapshot_id: str
    fetched_at_utc: str
    account_index: int
    l1_address: str
    collateral: Decimal
    available_balance: Decimal
    total_asset_value: Decimal | None
    source_transaction_time: str | None
    position_count: int
    positions: tuple[PositionObservation, ...]


def get_account_snapshots(
    account_index: int,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 2,
) -> list[StoredAccountSnapshot]:
    if limit <= 0:
        raise ValueError("limit harus positif")
    if not Path(db_path).is_file():
        raise FileNotFoundError(f"Database belum ada: {db_path}")
    with closing(_connect(db_path)) as conn:
        runs = conn.execute("""SELECT * FROM account_snapshots WHERE account_index = ?
            ORDER BY fetched_at_utc DESC, rowid DESC LIMIT ?""",
            (integer(account_index, "account_index"), limit)).fetchall()
        result = []
        for run in runs:
            rows = conn.execute("""SELECT * FROM position_snapshots
                WHERE snapshot_id = ? ORDER BY market_id""", (run["snapshot_id"],)).fetchall()
            positions = tuple(PositionObservation(
                market_id=p["market_id"], symbol=p["symbol"], raw_sign=p["raw_sign"],
                quantity=Decimal(p["quantity"]), avg_entry_price=Decimal(p["avg_entry_price"]),
                position_value=Decimal(p["position_value"]),
                unrealized_pnl=Decimal(p["unrealized_pnl"]),
                realized_pnl=Decimal(p["realized_pnl"]),
                liquidation_price=Decimal(p["liquidation_price"]) if p["liquidation_price"] is not None else None,
                margin_mode=p["margin_mode"],
                allocated_margin=Decimal(p["allocated_margin"]) if p["allocated_margin"] is not None else None,
            ) for p in rows)
            if len(positions) != run["position_count"]:
                raise RuntimeError("Snapshot tidak konsisten: jumlah posisi tidak cocok")
            result.append(StoredAccountSnapshot(
                snapshot_id=run["snapshot_id"], fetched_at_utc=run["fetched_at_utc"],
                account_index=run["account_index"], l1_address=run["l1_address"],
                collateral=Decimal(run["collateral"]),
                available_balance=Decimal(run["available_balance"]),
                total_asset_value=(Decimal(run["total_asset_value"])
                                   if run["total_asset_value"] is not None else None),
                source_transaction_time=run["source_transaction_time"],
                position_count=run["position_count"], positions=positions,
            ))
    return result
