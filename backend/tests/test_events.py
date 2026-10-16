import asyncio
import json

import pytest
from fastapi import HTTPException

from test_api import make_client


def test_event_batches_follow_insert_order_across_uuid_and_clock_changes(tmp_path):
    make_client(tmp_path)
    from skyweaver.db import session
    from skyweaver.services.events import event_cursor, read_event_batch

    with session() as conn:
        conn.execute("DELETE FROM events")
        # Both the UUID order and clock move backwards across the first batch.
        ids = [f"{100-index:03d}" for index in range(25)]
        for index, event_id in enumerate(ids):
            conn.execute("INSERT INTO events (id,type,payload,created_at) VALUES (?, 'capture', '{}', ?)", (event_id, "2026-10-16T10:00:00Z" if index < 20 else "2026-10-16T09:00:00Z"))
    first = read_event_batch(0)
    second = read_event_batch(first[-1]["sequence"])
    assert [row["id"] for row in first + second] == ids
    assert read_event_batch(second[-1]["sequence"]) == []
    assert [row["id"] for row in read_event_batch(event_cursor(ids[19]))] == ids[20:]


def test_sse_frames_include_resume_id_and_decoded_payload(tmp_path):
    make_client(tmp_path)
    from skyweaver.db import event, session
    from skyweaver.services.events import event_cursor, stream_events

    with session() as conn:
        previous = event(conn, "previous")
        current = event(conn, "new_image", {"image_id": "image-1"})

    async def first_frame():
        stream = stream_events(event_cursor(previous["id"]))
        try:
            return await anext(stream)
        finally:
            await stream.aclose()

    frame = asyncio.run(first_frame())
    assert frame.startswith(f"id: {current['id']}\nevent: new_image\n")
    payload = json.loads(frame.split("data: ", 1)[1])
    assert payload["payload"] == {"image_id": "image-1"}
    assert "sequence" not in payload
    with pytest.raises(HTTPException) as error:
        event_cursor("unknown-event")
    assert error.value.status_code == 400
