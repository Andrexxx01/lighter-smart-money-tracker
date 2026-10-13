"""Read-only: wallet L1 -> seluruh account index -> snapshot posisi SQLite.

Contoh:
  PYTHONPATH=src python scripts/discover_and_track_accounts.py --from-leaderboard 3
  PYTHONPATH=src python scripts/discover_and_track_accounts.py --l1-address 0x...
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from lighter_tracker.collectors.account_tracking import (
    discover_accounts, fetch_account_observation,
)
from lighter_tracker.normalizers.account_tracking import address_of
from lighter_tracker.storage.account_tracking_store import (
    DEFAULT_DB_PATH, save_account_snapshot, save_discovery,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lighter account discovery + posisi read-only")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--l1-address", help="Alamat L1 wallet 0x... (40 hex)")
    source.add_argument("--from-leaderboard", type=int, metavar="N",
                        help="Gunakan N alamat unik dari snapshot leaderboard terbaru")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--max-accounts", type=int, default=20,
                        help="Batas account per wallet; gagal jika terlampaui, bukan memotong data")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Jeda antarrequest dalam detik")
    args = parser.parse_args()
    if args.from_leaderboard is not None and not 1 <= args.from_leaderboard <= 20:
        parser.error("--from-leaderboard harus 1..20")
    if args.l1_address:
        try:
            args.l1_address = address_of(args.l1_address)
        except ValueError as exc:
            parser.error(str(exc))
    if args.max_pages < 1 or args.max_accounts < 1 or args.delay < 0:
        parser.error("max-pages/max-accounts harus positif, delay tidak negatif")
    return args


def get_target_addresses(args: argparse.Namespace) -> list[str]:
    if args.l1_address:
        return [args.l1_address]
    from lighter_tracker.storage.sqlite_store import get_recent_runs, get_run_entries
    runs = get_recent_runs(db_path=args.db, limit=1, time_window="all",
                           sort_by="pnl", sort_dir="desc")
    if not runs:
        raise RuntimeError("Belum ada snapshot leaderboard 'all/pnl/desc' di database")
    seen: set[str] = set()
    addresses: list[str] = []
    for row in get_run_entries(runs[0].run_id, db_path=args.db):
        addr = address_of(row.l1_address)
        if addr not in seen:
            addresses.append(addr)
            seen.add(addr)
        if len(addresses) >= args.from_leaderboard:
            break
    if not addresses:
        raise RuntimeError("Snapshot leaderboard terbaru tidak memiliki alamat")
    return addresses


async def main() -> None:
    args = parse_args()
    addresses = get_target_addresses(args)
    import lighter  # Import SDK hanya ketika live collection dijalankan

    client = lighter.ApiClient()
    account_api = lighter.AccountApi(client)
    try:
        for addr in addresses:
            print(f"\nWallet L1: {addr}")
            identities = await discover_accounts(account_api, addr, max_pages=args.max_pages)
            if len(identities) > args.max_accounts:
                raise RuntimeError(f"Ditemukan {len(identities)} account; melebihi --max-accounts")
            discovery_id = save_discovery(addr, identities, db_path=args.db)
            print(f"Discovery {discovery_id}: {len(identities)} account")
            for identity in identities:
                await asyncio.sleep(args.delay)
                observation = await fetch_account_observation(account_api, identity.account_index)
                if observation.l1_address != addr:
                    raise RuntimeError("Account detail mempunyai L1 address berbeda; dihentikan")
                snapshot_id = save_account_snapshot(observation, db_path=args.db)
                print(f"  account={identity.account_index} posisi_aktif={len(observation.positions)} "
                      f"snapshot={snapshot_id}")
                for p in observation.positions:
                    print(f"    {p.symbol} market={p.market_id} sign_raw={p.raw_sign} "
                          f"size={p.quantity} value={p.position_value} uPnL={p.unrealized_pnl}")
            await asyncio.sleep(args.delay)
    finally:
        await client.close()
    print("\nSelesai. Tidak ada order atau transaksi yang dikirim.")


if __name__ == "__main__":
    asyncio.run(main())
