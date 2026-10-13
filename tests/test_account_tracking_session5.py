"""Semua tes offline: SDK / jaringan tidak dibutuhkan."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace as NS

from lighter_tracker.collectors.account_tracking import discover_accounts, fetch_account_observation
from lighter_tracker.normalizers.account_tracking import (
    AccountIdentity, normalize_detailed_account, normalize_sub_accounts,
)
from lighter_tracker.normalizers.position_changes import compare_position_snapshots
from lighter_tracker.storage.account_tracking_store import (
    get_account_snapshots, save_account_snapshot, save_discovery,
)

ADDR = "0x" + "a" * 40
OTHER = "0x" + "b" * 40


def p(market=1, size="0.5", value="50000", sign=1, symbol="BTC"):
    return NS(market_id=market, symbol=symbol, sign=sign, position=size,
              avg_entry_price="100000", position_value=value,
              unrealized_pnl="12.123456789123456789", realized_pnl="10",
              liquidation_price="80000", margin_mode=0, allocated_margin="1000")


def account(index=101, positions=None, address=ADDR):
    return NS(index=index, l1_address=address, collateral="10000.123456789123456789",
              available_balance="8000", total_asset_value="11000", transaction_time=1720000000,
              positions=positions if positions is not None else [p()])


class FakeApi:
    def __init__(self):
        self.discovery_calls = []
        self.detail_calls = []

    async def accounts_by_l1_address(self, *, l1_address, cursor=None):
        self.discovery_calls.append((l1_address, cursor))
        if cursor is None:
            return NS(sub_accounts=[NS(index=101, l1_address=ADDR)], next_cursor="page2")
        return NS(sub_accounts=[NS(index=205, l1_address=ADDR)], next_cursor=None)

    async def account(self, *, by, value):
        self.detail_calls.append((by, value))
        return NS(accounts=[account(int(value))])


class Session5Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "tracker.sqlite3"

    def test_discovery_paginates_and_preserves_multiple_accounts(self):
        api = FakeApi()
        result = asyncio.run(discover_accounts(api, ADDR))
        self.assertEqual([x.account_index for x in result], [101, 205])
        self.assertEqual(api.discovery_calls, [(ADDR, None), (ADDR, "page2")])

    def test_discovery_empty_is_valid(self):
        self.assertEqual(normalize_sub_accounts(NS(sub_accounts=[]), ADDR), ())

    def test_missing_sub_accounts_is_not_treated_as_empty(self):
        with self.assertRaises(ValueError):
            normalize_sub_accounts(NS(), ADDR)

    def test_mismatched_address_rejected(self):
        with self.assertRaises(ValueError):
            normalize_sub_accounts(NS(sub_accounts=[NS(index=101, l1_address=OTHER)]), ADDR)

    def test_discovery_cursor_loop_detected(self):
        class LoopApi:
            async def accounts_by_l1_address(self, *, l1_address, cursor=None):
                return NS(sub_accounts=[], next_cursor="again")
        with self.assertRaises(RuntimeError):
            asyncio.run(discover_accounts(LoopApi(), ADDR))

    def test_fetch_account_index_exact(self):
        obs = asyncio.run(fetch_account_observation(FakeApi(), 205))
        self.assertEqual(obs.account_index, 205)
        self.assertEqual(len(obs.positions), 1)

    def test_wrong_account_index_rejected(self):
        with self.assertRaises(ValueError):
            normalize_detailed_account(NS(accounts=[account(205)]), 101)

    def test_missing_positions_rejected(self):
        a = account()
        del a.positions
        with self.assertRaises(ValueError):
            normalize_detailed_account(NS(accounts=[a]), 101)

    def test_zero_positions_are_valid(self):
        obs = normalize_detailed_account(NS(accounts=[account(positions=[p(size="0")])]), 101)
        self.assertEqual(obs.positions, ())
        save_account_snapshot(obs, db_path=self.db)
        self.assertEqual(get_account_snapshots(101, db_path=self.db)[0].position_count, 0)

    def test_decimal_roundtrip(self):
        obs = normalize_detailed_account(NS(accounts=[account()]), 101)
        save_account_snapshot(obs, db_path=self.db)
        restored = get_account_snapshots(101, db_path=self.db)[0]
        self.assertEqual(restored.collateral, Decimal("10000.123456789123456789"))
        self.assertEqual(restored.positions[0].unrealized_pnl,
                         Decimal("12.123456789123456789"))

    def test_discovery_storage_preserves_empty_run(self):
        run = save_discovery(ADDR, [], db_path=self.db)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT account_count FROM account_discovery_runs WHERE run_id=?",
                                          (run,)).fetchone()[0], 0)

    def test_discovery_rejects_duplicate_account_index(self):
        with self.assertRaises(ValueError):
            save_discovery(ADDR, [AccountIdentity(ADDR, 101), AccountIdentity(ADDR, 101)],
                           db_path=self.db)

    def test_price_change_does_not_look_like_size_increase(self):
        first = normalize_detailed_account(NS(accounts=[account(positions=[p(value="50000")])]), 101)
        second = normalize_detailed_account(NS(accounts=[account(positions=[p(value="52500")])]), 101)
        t1 = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
        save_account_snapshot(first, db_path=self.db, fetched_at=t1)
        save_account_snapshot(second, db_path=self.db, fetched_at=t2)
        latest, earlier = get_account_snapshots(101, db_path=self.db)
        change = compare_position_snapshots(earlier, latest)[0]
        self.assertEqual(change.event, "SIZE_UNCHANGED")
        self.assertEqual(change.current_value - change.previous_value, Decimal("2500"))

    def test_size_increase(self):
        a = normalize_detailed_account(NS(accounts=[account(positions=[p(size="0.5")])]), 101)
        b = normalize_detailed_account(NS(accounts=[account(positions=[p(size="0.8")])]), 101)
        self.assertEqual(compare_position_snapshots(a, b)[0].event, "SIZE_INCREASED")

    def test_sign_change_requires_review(self):
        a = normalize_detailed_account(NS(accounts=[account(positions=[p(sign=1)])]), 101)
        b = normalize_detailed_account(NS(accounts=[account(positions=[p(sign=-1)])]), 101)
        self.assertEqual(compare_position_snapshots(a, b)[0].event, "RAW_SIGN_CHANGED_REVIEW")

    def test_position_disappears_when_empty_snapshot_is_complete(self):
        a = normalize_detailed_account(NS(accounts=[account()]), 101)
        b = normalize_detailed_account(NS(accounts=[account(positions=[])]), 101)
        self.assertEqual(compare_position_snapshots(a, b)[0].event, "POSITION_DISAPPEARED")

    def test_no_cross_account_comparison(self):
        a = normalize_detailed_account(NS(accounts=[account(101)]), 101)
        b = normalize_detailed_account(NS(accounts=[account(205)]), 205)
        with self.assertRaises(ValueError):
            compare_position_snapshots(a, b)

    def test_bad_timestamp_rejected(self):
        a = normalize_detailed_account(NS(accounts=[account()]), 101)
        with self.assertRaises(ValueError):
            save_account_snapshot(a, db_path=self.db, fetched_at=datetime(2026, 10, 10))

    def test_session4_tables_are_not_touched(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE leaderboard_runs (id TEXT)")
            conn.execute("INSERT INTO leaderboard_runs VALUES ('preserve')")
        obs = normalize_detailed_account(NS(accounts=[account()]), 101)
        save_account_snapshot(obs, db_path=self.db)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT id FROM leaderboard_runs").fetchone()[0], "preserve")


if __name__ == "__main__":
    unittest.main()
