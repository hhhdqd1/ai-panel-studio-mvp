from __future__ import annotations

import re

from app.store import empty_insight


ALLOWED_REASONS = {"record_conflict", "unsupported_source", "needs_external_check"}
OPINION_PREFIXES = ("我认为", "我觉得", "我主张", "应该", "更公平", "更重要")
CHECKABLE_MARKERS = re.compile(r"\d|《[^》]+》|[“\"][^”\"]+[”\"]|研究表明|数据显示|据.+报道")


def valid_flag(
    flag: dict, known_message_ids: set[str], message_contents: dict[str, str] | None = None
) -> bool:
    quote = str(flag.get("quote", "")).strip()
    message_id = flag.get("message_id")
    if message_id not in known_message_ids:
        return False
    if flag.get("reason_code") not in ALLOWED_REASONS:
        return False
    if flag.get("status") not in {"open", "clarified"}:
        return False
    if not 4 <= len(quote) <= 160 or quote.startswith(OPINION_PREFIXES):
        return False
    if message_contents is not None and quote not in message_contents.get(message_id, ""):
        return False
    if flag["reason_code"] == "record_conflict":
        other_id = flag.get("conflicts_with_message_id")
        return other_id in known_message_ids and other_id != message_id
    return bool(CHECKABLE_MARKERS.search(quote))


def _sourced_items(raw: object, known_message_ids: set[str], *, min_sources: int) -> list[dict]:
    if not isinstance(raw, list):
        return []
    items: list[dict] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()[:400]
        source_ids = item.get("message_ids")
        if not isinstance(source_ids, list) or not text:
            continue
        ids = list(dict.fromkeys(source_ids))
        if len(ids) < min_sources or any(source_id not in known_message_ids for source_id in ids):
            continue
        key = (text, tuple(ids))
        if key in seen:
            continue
        seen.add(key)
        items.append({"text": text, "message_ids": ids})
    return items


def sanitize_review(
    raw: dict,
    known_message_ids: set[str],
    message_contents: dict[str, str] | None = None,
) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("review must be an object")
    result = empty_insight()
    result["consensus"] = _sourced_items(raw.get("consensus"), known_message_ids, min_sources=2)
    result["disagreements"] = _sourced_items(raw.get("disagreements"), known_message_ids, min_sources=2)
    result["open_questions"] = _sourced_items(raw.get("open_questions"), known_message_ids, min_sources=1)

    flags = raw.get("claim_flags")
    seen_flags: set[tuple[str, str]] = set()
    if isinstance(flags, list):
        for flag in flags:
            if not isinstance(flag, dict) or not valid_flag(flag, known_message_ids, message_contents):
                continue
            key = (flag["message_id"], flag["quote"].strip())
            if key in seen_flags:
                continue
            seen_flags.add(key)
            cleaned = {
                "message_id": key[0],
                "quote": key[1],
                "reason_code": flag["reason_code"],
                "explanation": str(flag.get("explanation", "")).strip()[:240],
                "status": flag["status"],
            }
            if flag["reason_code"] == "record_conflict":
                cleaned["conflicts_with_message_id"] = flag["conflicts_with_message_id"]
            result["claim_flags"].append(cleaned)
    return result


def merge_insight(previous: dict, latest: dict) -> dict:
    merged = {"consensus": [], "disagreements": [], "open_questions": [], "claim_flags": []}
    for category in ("consensus", "disagreements", "open_questions"):
        items = {}
        for item in [*previous.get(category, []), *latest.get(category, [])]:
            items[item["text"]] = item
        merged[category] = list(items.values())[-8:]
    flags: dict[tuple[str, str], dict] = {}
    for flag in previous.get("claim_flags", []):
        flags[(flag["message_id"], flag["quote"])] = flag
    for flag in latest.get("claim_flags", []):
        flags[(flag["message_id"], flag["quote"])] = flag
    merged["claim_flags"] = list(flags.values())
    return merged
