"""Perbandingan snapshot ukuran posisi, bukan rekonstruksi fill/trade."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from lighter_tracker.normalizers.account_tracking import PositionObservation


class HasPositions(Protocol):
    account_index: int
    positions: tuple[PositionObservation, ...]


@dataclass(frozen=True)
class PositionChange:
    market_id: int
    symbol: str
    event: str
    previous_size: Decimal
    current_size: Decimal
    previous_value: Decimal
    current_value: Decimal
    previous_raw_sign: int | None
    current_raw_sign: int | None


def compare_position_snapshots(previous: HasPositions, current: HasPositions) -> tuple[PositionChange, ...]:
    if previous.account_index != current.account_index:
        raise ValueError("Tidak boleh membandingkan account index berbeda")
    before = {p.market_id: p for p in previous.positions}
    after = {p.market_id: p for p in current.positions}
    changes: list[PositionChange] = []
    for market in sorted(before.keys() | after.keys()):
        old = before.get(market)
        new = after.get(market)
        if old is None:
            event = "POSITION_APPEARED"
        elif new is None:
            event = "POSITION_DISAPPEARED"
        elif old.raw_sign != new.raw_sign:
            event = "RAW_SIGN_CHANGED_REVIEW"
        elif abs(new.quantity) > abs(old.quantity):
            event = "SIZE_INCREASED"
        elif abs(new.quantity) < abs(old.quantity):
            event = "SIZE_DECREASED"
        else:
            event = "SIZE_UNCHANGED"
        changes.append(PositionChange(
            market_id=market, symbol=(new or old).symbol, event=event,
            previous_size=abs(old.quantity) if old else Decimal("0"),
            current_size=abs(new.quantity) if new else Decimal("0"),
            previous_value=old.position_value if old else Decimal("0"),
            current_value=new.position_value if new else Decimal("0"),
            previous_raw_sign=old.raw_sign if old else None,
            current_raw_sign=new.raw_sign if new else None,
        ))
    return tuple(changes)
