import asyncio

from zoneinfo import ZoneInfo

from lighter_tracker.collectors.lighter_rest import (
    LighterRestCollector,
)


async def main():

    collector = LighterRestCollector()

    try:
        page = (
            await collector.get_pnl_leaderboard_page(
                limit=3
            )
        )

        wib = ZoneInfo(
            "Asia/Jakarta"
        )

        print(
            "Total leaderboard:",
            page.total,
        )

        print(
            "Data updated (WIB):",
            page.updated_at.astimezone(wib),
        )

        print(
            "Fetched (WIB):",
            page.fetched_at.astimezone(wib),
        )

        for candidate in page.candidates:

            print(
                "\n" + "=" * 55
            )

            print(
                "Rank:",
                candidate.rank,
            )

            print(
                "L1 address:",
                candidate.l1_address,
            )

            print(
                "PnL (raw):",
                candidate.pnl,
            )

            print(
                "ROI (raw):",
                candidate.roi,
            )

            references = await (
                collector.get_accounts_by_l1_address(
                    candidate.l1_address
                )
            )

            if not references:

                print(
                    "Tidak ada account pada response ini"
                )

                continue

            for ref in references:

                print(
                    "Account index:",
                    ref.account_index,

                    "| type:",
                    ref.account_type,

                    "| mode:",
                    ref.trading_mode,

                    "| status:",
                    ref.status,
                )

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())