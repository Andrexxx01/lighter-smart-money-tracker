from lighter_tracker.models.account import (
    to_decimal,
)

from lighter_tracker.models.trader import (
    TraderCandidate,
)


def normalize_trader_candidate(
    raw_entry,
) -> TraderCandidate:
    return TraderCandidate(
        rank=raw_entry.rank,
        l1_address=raw_entry.l1_address,
        account_value=to_decimal(
            raw_entry.account_value
        ),
        pnl=to_decimal(
            raw_entry.pnl
        ),
        roi=to_decimal(
            raw_entry.roi
        ),
        volume=to_decimal(
            raw_entry.volume
        ),
    )