import asyncio
from pprint import pprint

from lighter_tracker.collectors.lighter_rest import (
    LighterRestCollector,
)


async def main():
    collector = LighterRestCollector()

    try:
        candidates = (
            await collector.get_pnl_leaderboard(
                time_window="all",
                sort_by="pnl",
                sort_dir="desc",
                limit=10,
                offset=0,
            )
        )

        for candidate in candidates:
            pprint(candidate)

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())