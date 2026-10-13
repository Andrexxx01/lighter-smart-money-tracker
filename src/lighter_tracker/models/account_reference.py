from dataclasses import dataclass


@dataclass(frozen=True)
class AccountReference:
    account_index: int

    l1_address: str

    account_type: int

    trading_mode: int

    status: int