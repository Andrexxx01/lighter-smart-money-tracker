"""SDK adapter read-only; semua API calls disediakan oleh caller."""
from __future__ import annotations

from typing import Any
from lighter_tracker.normalizers.account_tracking import (
    AccountIdentity, AccountObservation, address_of, field,
    normalize_detailed_account, normalize_sub_accounts,
)


async def discover_accounts(
    account_api: Any,
    l1_address: str,
    *,
    max_pages: int = 20,
) -> tuple[AccountIdentity, ...]:
    """Telusuri seluruh halaman. Gagal keras pada cursor loop / respons parsial."""
    address = address_of(l1_address)
    if max_pages <= 0:
        raise ValueError("max_pages harus positif")
    cursor: str | None = None
    seen_cursors: set[str] = set()
    discovered: dict[int, AccountIdentity] = {}
    for _ in range(max_pages):
        kwargs = {"l1_address": address}
        if cursor is not None:
            kwargs["cursor"] = cursor
        response = await account_api.accounts_by_l1_address(**kwargs)
        for identity in normalize_sub_accounts(response, address):
            existing = discovered.get(identity.account_index)
            if existing is not None and existing != identity:
                raise ValueError("Konflik account_index antarhalaman")
            discovered[identity.account_index] = identity
        next_cursor = field(response, "next_cursor")
        if next_cursor is None or str(next_cursor).strip() == "":
            return tuple(discovered[k] for k in sorted(discovered))
        next_cursor = str(next_cursor)
        if next_cursor == cursor or next_cursor in seen_cursors:
            raise RuntimeError("Cursor pagination berulang; hasil discovery tidak lengkap")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    raise RuntimeError("Batas max_pages tercapai; hasil discovery tidak lengkap")


async def fetch_account_observation(account_api: Any, account_index: int) -> AccountObservation:
    response = await account_api.account(by="index", value=str(account_index))
    return normalize_detailed_account(response, account_index)
