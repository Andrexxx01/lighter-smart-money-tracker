from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TraderCandidate:
    rank: int
    l1_address: str

    account_value: Decimal
    pnl: Decimal
    roi: Decimal
    volume: Decimal