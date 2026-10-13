from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Union


@dataclass(frozen=True)
class PositionSnapshot:
    market_id: int
    symbol: str

    sign: int

    size: Decimal
    position_value: Decimal

    avg_entry_price: Decimal
    liquidation_price: Decimal

    unrealized_pnl: Decimal
    realized_pnl: Decimal

    total_funding_paid_out: Decimal

ZERO = Decimal("0")


def to_decimal(
    value: Optional[Union[str, int, float]],
) -> Decimal:
    if value is None:
        return ZERO

    return Decimal(str(value))

@dataclass(frozen=True)
class AccountSnapshot:
    account_index: int
    l1_address: str

    available_balance: Decimal
    collateral: Decimal

    positions: tuple[PositionSnapshot, ...]