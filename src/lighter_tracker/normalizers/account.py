from lighter_tracker.models.account import (
    AccountSnapshot,
    PositionSnapshot,
    to_decimal,
)


def normalize_position(
    raw_position,
) -> PositionSnapshot:
    return PositionSnapshot(
        market_id=raw_position.market_id,
        symbol=raw_position.symbol,
        sign=raw_position.sign,
        size=to_decimal(
            raw_position.position
        ),
        position_value=to_decimal(
            raw_position.position_value
        ),
        avg_entry_price=to_decimal(
            raw_position.avg_entry_price
        ),
        liquidation_price=to_decimal(
            raw_position.liquidation_price
        ),
        unrealized_pnl=to_decimal(
            raw_position.unrealized_pnl
        ),
        realized_pnl=to_decimal(
            raw_position.realized_pnl
        ),
        total_funding_paid_out=to_decimal(
            raw_position.total_funding_paid_out
        ),
    )

def normalize_account(
    raw_account,
) -> AccountSnapshot:
    positions = tuple(
        normalize_position(position)
        for position in raw_account.positions
    )

    return AccountSnapshot(
        account_index=raw_account.index,
        l1_address=raw_account.l1_address,
        available_balance=to_decimal(
            raw_account.available_balance
        ),
        collateral=to_decimal(
            raw_account.collateral
        ),
        positions=positions,
    )