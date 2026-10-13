"""Penyimpanan snapshot leaderboard Lighter menggunakan SQLite.

Tidak memerlukan dependency tambahan; angka finansial disimpan sebagai TEXT
agar presisi Decimal tidak hilang akibat konversi ke SQLite REAL.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sqlite3
from typing import Iterable
from uuid import uuid4

from lighter_tracker.models.trader import TraderCandidate

DEFAULT_DB_PATH = Path("data/lighter_tracker.sqlite3")
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-f]{40}$")


@dataclass(frozen=True)
class StoredLeaderboardRun:
    run_id: str
    fetched_at_utc: str
    source_updated_at_utc: str | None
    time_window: str
    sort_by: str
    sort_dir: str
    requested_limit: int
    requested_offset: int
    entry_count: int


@dataclass(frozen=True)
class StoredLeaderboardEntry:
    run_id: str
    rank: int
    l1_address: str
    account_value: Decimal
    pnl: Decimal
    roi: Decimal
    volume: Decimal


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Buat skema jika belum ada; aman dipanggil berulang kali."""
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS leaderboard_runs (
                    run_id TEXT PRIMARY KEY,
                    fetched_at_utc TEXT NOT NULL,
                    source_updated_at_utc TEXT,
                    time_window TEXT NOT NULL,
                    sort_by TEXT NOT NULL,
                    sort_dir TEXT NOT NULL,
                    requested_limit INTEGER NOT NULL CHECK (requested_limit > 0),
                    requested_offset INTEGER NOT NULL CHECK (requested_offset >= 0),
                    entry_count INTEGER NOT NULL CHECK (entry_count > 0)
                );

                CREATE TABLE IF NOT EXISTS leaderboard_entries (
                    run_id TEXT NOT NULL,
                    rank INTEGER NOT NULL CHECK (rank > 0),
                    l1_address TEXT NOT NULL,
                    account_value TEXT NOT NULL,
                    pnl TEXT NOT NULL,
                    roi TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    PRIMARY KEY (run_id, rank),
                    FOREIGN KEY (run_id) REFERENCES leaderboard_runs(run_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_leaderboard_runs_scope_time
                ON leaderboard_runs(time_window, sort_by, sort_dir, fetched_at_utc DESC);

                CREATE INDEX IF NOT EXISTS idx_leaderboard_entries_address
                ON leaderboard_entries(l1_address);
                """
            )


def _utc_iso(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp harus timezone-aware (misalnya UTC).")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _decimal_text(value: object, field: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Nilai {field} tidak valid: {value!r}") from exc
    if not number.is_finite():
        raise ValueError(f"Nilai {field} harus finite, bukan NaN/Infinity.")
    return str(number)


def _entry_values(run_id: str, entry: TraderCandidate) -> tuple:
    address = str(entry.l1_address).strip().lower()
    if not ADDRESS_PATTERN.fullmatch(address):
        raise ValueError(f"Alamat L1 tidak valid: {entry.l1_address!r}")
    rank = int(entry.rank)
    if rank <= 0:
        raise ValueError("Rank harus lebih besar dari nol.")
    return (
        run_id,
        rank,
        address,
        _decimal_text(entry.account_value, "account_value"),
        _decimal_text(entry.pnl, "pnl"),
        _decimal_text(entry.roi, "roi"),
        _decimal_text(entry.volume, "volume"),
    )


def save_leaderboard_snapshot(
    candidates: Iterable[TraderCandidate],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    time_window: str = "all",
    sort_by: str = "pnl",
    sort_dir: str = "desc",
    requested_limit: int = 20,
    requested_offset: int = 0,
    fetched_at: datetime | None = None,
    source_updated_at: datetime | None = None,
) -> str:
    """Simpan satu hasil pengambilan leaderboard secara atomik.

    Setiap pemanggilan membuat run_id baru. Dua pengambilan yang datanya
    identik tetap dua observasi, bukan dua transaksi/dua kejadian trading.
    """
    candidates = tuple(candidates)
    if not candidates:
        raise ValueError("Snapshot kosong tidak disimpan sebagai observasi valid.")
    if requested_limit <= 0 or requested_offset < 0:
        raise ValueError("requested_limit/offset tidak valid.")
    if len(candidates) > requested_limit:
        raise ValueError("Jumlah entri melebihi requested_limit.")
    if not all((time_window, sort_by, sort_dir)):
        raise ValueError("Parameter scope leaderboard tidak boleh kosong.")

    run_id = uuid4().hex
    fetched_at_utc = _utc_iso(fetched_at)
    source_updated_at_utc = (
        _utc_iso(source_updated_at) if source_updated_at is not None else None
    )
    rows = [_entry_values(run_id, entry) for entry in candidates]
    ranks = [row[1] for row in rows]
    if len(ranks) != len(set(ranks)):
        raise ValueError("Terdapat rank duplikat dalam satu snapshot.")

    init_db(db_path)
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO leaderboard_runs (
                    run_id, fetched_at_utc, source_updated_at_utc,
                    time_window, sort_by, sort_dir,
                    requested_limit, requested_offset, entry_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id, fetched_at_utc, source_updated_at_utc,
                    time_window, sort_by, sort_dir,
                    requested_limit, requested_offset, len(rows),
                ),
            )
            conn.executemany(
                """
                INSERT INTO leaderboard_entries (
                    run_id, rank, l1_address, account_value, pnl, roi, volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
    return run_id


def _require_existing_db(db_path: str | Path) -> None:
    if not Path(db_path).is_file():
        raise FileNotFoundError(f"Database belum ada: {db_path}")


def get_recent_runs(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 5,
    time_window: str | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
) -> list[StoredLeaderboardRun]:
    if limit <= 0:
        raise ValueError("limit harus positif.")
    _require_existing_db(db_path)
    clauses: list[str] = []
    params: list[object] = []
    for column, value in (
        ("time_window", time_window),
        ("sort_by", sort_by),
        ("sort_dir", sort_dir),
    ):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT * FROM leaderboard_runs {where}
        ORDER BY fetched_at_utc DESC, rowid DESC
        LIMIT ?
    """
    params.append(limit)
    with closing(_connect(db_path)) as conn:
        result = conn.execute(sql, params).fetchall()
    return [StoredLeaderboardRun(**dict(row)) for row in result]


def get_run_entries(
    run_id: str,
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[StoredLeaderboardEntry]:
    _require_existing_db(db_path)
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT * FROM leaderboard_entries WHERE run_id = ? ORDER BY rank ASC",
            (run_id,),
        ).fetchall()
    return [
        StoredLeaderboardEntry(
            run_id=row["run_id"],
            rank=row["rank"],
            l1_address=row["l1_address"],
            account_value=Decimal(row["account_value"]),
            pnl=Decimal(row["pnl"]),
            roi=Decimal(row["roi"]),
            volume=Decimal(row["volume"]),
        )
        for row in rows
    ]
