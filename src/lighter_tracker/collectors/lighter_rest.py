import lighter
from datetime import datetime, timezone
from lighter_tracker.normalizers.account import (
    normalize_account,
)

from lighter_tracker.normalizers.trader import (
    normalize_trader_candidate,
)

from lighter_tracker.normalizers.account_reference import (
    normalize_account_reference,
)

from lighter_tracker.models.leaderboard import (
    LeaderboardPage,
)

class LighterRestCollector:
    def __init__(self):
        self.client = lighter.ApiClient()

        self.account_api = lighter.AccountApi(
            self.client
        )

    async def get_account(
        self,
        account_index: int,
    ):
        response = await self.account_api.account(
            by="index",
            value=str(account_index),
        )

        if not response.accounts:
            return None

        raw_account = response.accounts[0]

        return normalize_account(
            raw_account
        )
    
    async def get_pnl_leaderboard(
        self,
        time_window: str = "all",
        sort_by: str = "pnl",
        sort_dir: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ):
        response = (
            await self.account_api.pnl_leaderboard(
                time_window=time_window,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            )
        )

        return tuple(
            normalize_trader_candidate(entry)
            for entry in response.entries
        ) 
    
    async def get_pnl_leaderboard_page(
        self,
        time_window: str = "all",
        sort_by: str = "pnl",
        sort_dir: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> LeaderboardPage:

        response = await (
            self.account_api.pnl_leaderboard(
                time_window=time_window,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            )
        )
    

        if response.code != 200:
            raise RuntimeError(
                f"PnL leaderboard API code={response.code}"
            )

        return LeaderboardPage(
            total=response.total,
            updated_at=datetime.fromtimestamp(
                response.updated_at,
                tz=timezone.utc,
            ),
            fetched_at=datetime.now(
                timezone.utc
            ),

            candidates=tuple(
                normalize_trader_candidate(entry)
                for entry in (response.entries or [])
            ),
        )

    async def get_accounts_by_l1_address(
        self,
        l1_address: str,
        max_pages: int = 5,
    ) -> tuple:

        if max_pages < 1:
            raise ValueError(
                "max_pages harus >= 1"
            )

        accounts = []

        cursor = None

        seen_cursors = set()

        for _ in range(max_pages):

            kwargs = {
                "l1_address": l1_address
            }

            if cursor is not None:
                kwargs["cursor"] = cursor

            response = await (
                self.account_api.accounts_by_l1_address(
                    **kwargs
                )
            )

            if response.code != 200:
                raise RuntimeError(
                    f"AccountsByL1Address API code={response.code}"
                )

            accounts.extend(
                normalize_account_reference(account)
                for account in (response.sub_accounts or [])
            )

            next_cursor = response.next_cursor

            if not next_cursor:
                return tuple(accounts)

            if next_cursor in seen_cursors:
                raise RuntimeError(
                    "Cursor pagination berulang"
                )

            seen_cursors.add(next_cursor)

            cursor = next_cursor

        raise RuntimeError(
            f"Pagination belum selesai setelah {max_pages} halaman"
        )  

    async def close(self):
        await self.client.close()