import asyncio

from lighter_tracker.collectors.lighter_rest import (
    LighterRestCollector,
)


async def main():
    collector = LighterRestCollector()

    try:
        account = await collector.get_account(
            account_index=1
        )

        print(account)

    finally:
        await collector.close()


if __name__ == "__main__":
    asyncio.run(main())