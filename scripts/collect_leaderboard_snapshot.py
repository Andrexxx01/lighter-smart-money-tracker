"""Ambil leaderboard Lighter dan simpan sebagai snapshot SQLite.

Jalankan dari root proyek:
python scripts/collect_leaderboard_snapshot.py --limit 10
"""

import argparse
import asyncio
from pathlib import Path

from lighter_tracker.collectors.lighter_rest import LighterRestCollector
from lighter_tracker.storage.sqlite_store import (
    DEFAULT_DB_PATH,
    save_leaderboard_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simpan snapshot leaderboard Lighter")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--window", default="all", help="Time window API (default: all)")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit harus 1 sampai 100")
    if args.offset < 0:
        parser.error("--offset tidak boleh negatif")
    return args


async def main() -> None:
    args = parse_args()
    collector = LighterRestCollector()
    try:
        candidates = await collector.get_pnl_leaderboard(
            time_window=args.window,
            sort_by="pnl",
            sort_dir="desc",
            limit=args.limit,
            offset=args.offset,
        )
    finally:
        await collector.close()

    if not candidates:
        raise RuntimeError("API mengembalikan leaderboard kosong; tidak menyimpan snapshot.")

    run_id = save_leaderboard_snapshot(
        candidates,
        db_path=args.db,
        time_window=args.window,
        sort_by="pnl",
        sort_dir="desc",
        requested_limit=args.limit,
        requested_offset=args.offset,
    )
    print(f"Snapshot tersimpan: {run_id}")
    print(f"Database: {args.db.resolve()}")
    print(f"Jumlah entri: {len(candidates)}")
    for trader in candidates[:5]:
        print(
            f"#{trader.rank} {trader.l1_address} "
            f"PnL={trader.pnl} ROI(raw)={trader.roi}"
        )
    print("Catatan: ROI(raw) belum diubah ke persen karena unit API perlu divalidasi.")


if __name__ == "__main__":
    asyncio.run(main())
