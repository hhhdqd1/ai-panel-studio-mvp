from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from time import monotonic

from app.store import Store


def sse_frame(event: dict) -> str:
    return (
        f"id: {event['sequence']}\n"
        f"event: {event['type']}\n"
        f"data: {json.dumps(event['payload'], ensure_ascii=False)}\n\n"
    )


def parse_after(header: str | None, query: str | None) -> int:
    raw = header if header is not None else query
    if raw is None:
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError) as error:
        raise ValueError("after must be an integer") from error
    if value < 0:
        raise ValueError("after must be nonnegative")
    return value


async def event_frames(
    store: Store,
    discussion_id: str,
    after: int,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    cursor = after
    next_heartbeat = monotonic() + 15
    while not await is_disconnected():
        events = await store.events_after(discussion_id, cursor)
        if events:
            for event in events:
                cursor = event["sequence"]
                yield sse_frame(event)
            continue
        await store.wait_for_event(discussion_id, timeout=1.0)
        if monotonic() >= next_heartbeat:
            yield ": heartbeat\n\n"
            next_heartbeat = monotonic() + 15
