import asyncio

from .db import init_db, log, session


async def main() -> None:
    init_db()
    with session() as conn:
        log(conn, "info", "capture-daemon", "Capture daemon started", {})
    while True:
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
