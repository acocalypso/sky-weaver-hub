import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException

from ..db import json_loads, session


def event_cursor(last_event_id: str | None) -> int:
    if not last_event_id:
        return 0
    with session() as conn:
        row = conn.execute("SELECT rowid FROM events WHERE id=?", (last_event_id,)).fetchone()
    if row is None:
        raise HTTPException(400, "Unknown Last-Event-ID")
    return row["rowid"]


def read_event_batch(after_sequence: int, limit: int = 20) -> list[dict[str, Any]]:
    # UUIDs and wall-clock timestamps are not insertion-order cursors. The Pi's
    # clock can also move backwards when an offline operator corrects the time.
    with session() as conn:
        rows = conn.execute(
            "SELECT rowid AS sequence, * FROM events WHERE rowid > ? ORDER BY rowid LIMIT ?",
            (after_sequence, limit),
        ).fetchall()
    return [dict(row) for row in rows]


async def stream_events(after_sequence: int = 0, poll_seconds: float = 2) -> AsyncIterator[str]:
    while True:
        rows = read_event_batch(after_sequence)
        for row in rows:
            after_sequence = row.pop("sequence")
            row["payload"] = json_loads(row["payload"], {})
            yield f"id: {row['id']}\nevent: {row['type']}\ndata: {json.dumps(row)}\n\n"
        if len(rows) < 20:
            await asyncio.sleep(poll_seconds)
