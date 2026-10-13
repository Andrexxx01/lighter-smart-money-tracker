"""Bandingkan dua snapshot terbaru per account index (tanpa jaringan)."""
from __future__ import annotations
import argparse
from pathlib import Path

from lighter_tracker.normalizers.position_changes import compare_position_snapshots
from lighter_tracker.storage.account_tracking_store import DEFAULT_DB_PATH, get_account_snapshots


def main() -> None:
    parser = argparse.ArgumentParser(description="Bandingkan snapshot posisi Lighter")
    parser.add_argument("--account-index", type=int, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    snapshots = get_account_snapshots(args.account_index, db_path=args.db, limit=2)
    if len(snapshots) < 2:
        print("Belum cukup data: diperlukan dua snapshot account yang sama.")
        return
    newest, previous = snapshots
    print(f"Account: {args.account_index}")
    print(f"Sebelum: {previous.fetched_at_utc} | Setelah: {newest.fetched_at_utc}")
    print("CATATAN: ini perbandingan snapshot, bukan bukti order/fill atau arah trading.")
    for change in compare_position_snapshots(previous, newest):
        print(f"{change.symbol} market={change.market_id} {change.event}: "
              f"size {change.previous_size} -> {change.current_size}; "
              f"value {change.previous_value} -> {change.current_value}; "
              f"sign_raw {change.previous_raw_sign} -> {change.current_raw_sign}")


if __name__ == "__main__":
    main()
