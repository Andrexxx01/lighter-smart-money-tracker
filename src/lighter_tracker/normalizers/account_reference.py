from lighter_tracker.models.account_reference import (
    AccountReference,
)


def normalize_account_reference(
    raw_account,
) -> AccountReference:

    return AccountReference(
        account_index=raw_account.index,

        l1_address=raw_account.l1_address,

        account_type=raw_account.account_type,

        trading_mode=raw_account.account_trading_mode,

        status=raw_account.status,
    )