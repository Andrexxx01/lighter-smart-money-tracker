from types import SimpleNamespace

from lighter_tracker.normalizers.account_reference import (
    normalize_account_reference,
)


def test_normalize_account_reference():

    raw = SimpleNamespace(
        index=1234,

        l1_address="0x" + "a" * 40,

        account_type=1,

        account_trading_mode=0,

        status=1,
    )

    result = normalize_account_reference(
        raw
    )

    assert result.account_index == 1234

    assert result.account_type == 1

    assert result.trading_mode == 0