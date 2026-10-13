"""Demo end-to-end offline: tidak membutuhkan SDK atau koneksi jaringan."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

from lighter_tracker.normalizers.account_tracking import normalize_detailed_account
from lighter_tracker.normalizers.position_changes import compare_position_snapshots
from lighter_tracker.storage.account_tracking_store import get_account_snapshots, save_account_snapshot

ADDR = "0x" + "a" * 40


def position(size: str, value: str) -> NS:
    return NS(market_id=1, symbol="BTC", sign=1, position=size,
              avg_entry_price="100000", position_value=value,
              unrealized_pnl="0", realized_pnl="0", liquidation_price="80000",
              margin_mode=0, allocated_margin="10000")


def account(size: str, value: str) -> NS:
    return NS(index=101, l1_address=ADDR, collateral="20000",
              available_balance="10000", total_asset_value="20000",
              positions=[position(size, value)], transaction_time=1720000000)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/session5_demo.sqlite3"))
    args = parser.parse_args()
    start = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
    for hour, (size, value) in enumerate((("0.5", "50000"), ("0.5", "52500"), ("0.8", "84000"))):
        normalized = normalize_detailed_account(NS(accounts=[account(size, value)]), 101)
        run = save_account_snapshot(normalized, db_path=args.db,
                                    fetched_at=start + timedelta(hours=hour))
        print(f"Snapshot {hour + 1}: {run} size={size} value={value}")
    snapshots = get_account_snapshots(101, db_path=args.db, limit=3)
    chronological = list(reversed(snapshots))
    for earlier, later in zip(chronological, chronological[1:]):
        change = compare_position_snapshots(earlier, later)[0]
        print(f"{change.event}: size {change.previous_size}->{change.current_size}; "
              f"value {change.previous_value}->{change.current_value}")
    print(f"Database demo: {args.db.resolve()}")


if __name__ == "__main__":
    main()
