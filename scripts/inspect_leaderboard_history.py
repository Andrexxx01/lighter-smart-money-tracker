"""Baca histori snapshot leaderboard dari SQLite tanpa memanggil API."""

import argparse
from collections import Counter
from decimal import Decimal
from pathlib import Path

from lighter_tracker.storage.sqlite_store import (
    DEFAULT_DB_PATH,
    get_recent_runs,
    get_run_entries,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Periksa histori leaderboard")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--window", default="all")
    parser.add_argument("--last", type=int, default=3)
    parser.add_argument("--show", type=int, default=10)
    args = parser.parse_args()
    if args.last < 1 or args.show < 1:
        parser.error("--last dan --show harus positif")
    return args


def unique_addresses(entries):
    counts = Counter(item.l1_address for item in entries)
    return {item.l1_address: item for item in entries if counts[item.l1_address] == 1}


def main() -> None:
    args = parse_args()
    runs = get_recent_runs(
        db_path=args.db,
        limit=max(args.last, 2),
        time_window=args.window,
        sort_by="pnl",
        sort_dir="desc",
    )
    if not runs:
        print(f"Belum ada snapshot untuk window={args.window!r}.")
        return

    print(f"Database: {args.db.resolve()}")
    print("Histori pengambilan data (UTC):")
    for run in runs[:args.last]:
        print(f"  {run.fetched_at_utc} | {run.run_id[:12]} | {run.entry_count} trader")

    current = get_run_entries(runs[0].run_id, db_path=args.db)
    print("\nLeaderboard terbaru:")
    for entry in current[:args.show]:
        print(
            f"  #{entry.rank:>4} {entry.l1_address} "
            f"PnL={entry.pnl} ROI(raw)={entry.roi}"
        )

    if len(runs) < 2:
        print("\nPerbandingan belum tersedia: diperlukan minimal dua snapshot.")
        return

    previous = get_run_entries(runs[1].run_id, db_path=args.db)
    old_unique = unique_addresses(previous)
    new_unique = unique_addresses(current)
    print("\nPerubahan terhadap snapshot sebelumnya (alamat yang unik di kedua snapshot):")
    shown = 0
    for entry in current:
        if entry.l1_address not in new_unique:
            continue
        prior = old_unique.get(entry.l1_address)
        if prior is None:
            continue
        rank_improvement = prior.rank - entry.rank
        pnl_delta: Decimal = entry.pnl - prior.pnl
        print(
            f"  {entry.l1_address} | perubahan_rank={rank_improvement:+d} "
            f"| delta_PnL={pnl_delta:+f}"
        )
        shown += 1
        if shown >= args.show:
            break
    if not shown:
        print("  Tidak ada alamat unik yang muncul di kedua snapshot.")
    print(
        "\nPENTING: delta_PnL adalah selisih angka leaderboard, "
        "bukan bukti profit dari transaksi selama interval. "
        "Perubahan rank juga dipengaruhi trader lain."
    )


if __name__ == "__main__":
    main()
