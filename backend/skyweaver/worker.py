import asyncio

from .db import init_db, log, session
from .services.processing import run_once


async def main() -> None:
    init_db()
    with session() as conn:
        log(conn, "info", "worker", "Processing worker started", {})
    while True:
        try:
            processed = await run_once()
            await asyncio.sleep(0 if processed else 5)
        except Exception as exc:
            with session() as conn:
                log(conn, "error", "worker", "Processing worker loop failed", {"error": str(exc)})
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
