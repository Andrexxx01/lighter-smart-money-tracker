"""Unit test storage tanpa jaringan dan tanpa memanggil Lighter API."""

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from lighter_tracker.models.trader import TraderCandidate
from lighter_tracker.storage.sqlite_store import (
    get_recent_runs,
    get_run_entries,
    save_leaderboard_snapshot,
)


class LeaderboardStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "snapshots.sqlite3"

    def candidate(self, rank=1, address=None, pnl="12.123456789123456789"):
        if address is None:
            address = "0x" + f"{rank:040x}"
        return TraderCandidate(
            rank=rank,
            l1_address=address,
            account_value=Decimal("123456789.123456789123456789"),
            pnl=Decimal(pnl),
            roi=Decimal("0.123456789123456789"),
            volume=Decimal("999999.000000000000000001"),
        )

    def test_round_trip_preserves_decimal_and_normalizes_address(self):
        address = "0x" + "ABCDEF" * 6 + "ABCD"
        run_id = save_leaderboard_snapshot(
            [self.candidate(address=address)], db_path=self.db, requested_limit=1
        )
        entries = get_run_entries(run_id, db_path=self.db)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].l1_address, address.lower())
        self.assertEqual(entries[0].account_value, Decimal("123456789.123456789123456789"))
        self.assertEqual(entries[0].pnl, Decimal("12.123456789123456789"))
        self.assertEqual(entries[0].volume, Decimal("999999.000000000000000001"))

    def test_two_runs_keep_history_and_order(self):
        first = save_leaderboard_snapshot(
            [self.candidate(pnl="10")], db_path=self.db, requested_limit=1,
            fetched_at=datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc),
        )
        second = save_leaderboard_snapshot(
            [self.candidate(pnl="11")], db_path=self.db, requested_limit=1,
            fetched_at=datetime(2026, 10, 9, 9, 0, tzinfo=timezone.utc),
        )
        runs = get_recent_runs(db_path=self.db, limit=2, time_window="all")
        self.assertEqual([run.run_id for run in runs], [second, first])
        self.assertEqual(get_run_entries(first, db_path=self.db)[0].pnl, Decimal("10"))
        self.assertEqual(get_run_entries(second, db_path=self.db)[0].pnl, Decimal("11"))

    def test_empty_snapshot_rejected(self):
        with self.assertRaises(ValueError):
            save_leaderboard_snapshot([], db_path=self.db)
        self.assertFalse(self.db.exists())

    def test_duplicate_rank_rejected_before_write(self):
        with self.assertRaises(ValueError):
            save_leaderboard_snapshot(
                [self.candidate(rank=1), self.candidate(rank=1)],
                db_path=self.db, requested_limit=2,
            )
        self.assertFalse(self.db.exists())

    def test_duplicate_address_different_rank_is_not_silently_dropped(self):
        same_address = "0x" + "a" * 40
        run_id = save_leaderboard_snapshot(
            [self.candidate(rank=1, address=same_address),
             self.candidate(rank=2, address=same_address)],
            db_path=self.db, requested_limit=2,
        )
        self.assertEqual(len(get_run_entries(run_id, db_path=self.db)), 2)

    def test_non_finite_value_rejected(self):
        with self.assertRaises(ValueError):
            save_leaderboard_snapshot(
                [self.candidate(pnl="NaN")], db_path=self.db, requested_limit=1
            )

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            save_leaderboard_snapshot(
                [self.candidate()], db_path=self.db, requested_limit=1,
                fetched_at=datetime(2026, 10, 9, 9, 0),
            )

    def test_read_missing_db_does_not_create_file(self):
        with self.assertRaises(FileNotFoundError):
            get_recent_runs(db_path=self.db)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
