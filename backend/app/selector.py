from __future__ import annotations

import math


PUBLIC_FIELDS = (
    "agent_id",
    "wants_to_speak",
    "action",
    "target_message_id",
    "relevance",
    "novelty",
    "urgency",
    "public_intent",
)


def _unit(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return min(1.0, max(0.0, number))


def select_speaker(
    intents: list[dict], recent_agent_ids: list[str], spoken_counts: dict[str, int]
) -> dict | None:
    eligible = [
        item
        for item in intents
        if item.get("wants_to_speak") is True and isinstance(item.get("agent_id"), str)
    ]
    if not eligible:
        return None

    def score(item: dict) -> float:
        agent_id = item["agent_id"]
        value = (
            0.45 * _unit(item.get("relevance"))
            + 0.30 * _unit(item.get("novelty"))
            + 0.20 * _unit(item.get("urgency"))
        )
        if item.get("action") == "challenge" and item.get("target_message_id"):
            value += 0.08
        value -= 0.18 * recent_agent_ids[-2:].count(agent_id)
        value -= 0.03 * spoken_counts.get(agent_id, 0)
        if spoken_counts.get(agent_id, 0) == 0:
            value += 0.08
        return value

    chosen = sorted(eligible, key=lambda item: (-score(item), item["agent_id"]))[0]
    return {
        field: chosen.get(field)
        for field in PUBLIC_FIELDS
    }
