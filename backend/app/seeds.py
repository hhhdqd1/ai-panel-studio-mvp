from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid5

from app.model_gateway import validate_panel
from app.store import Store


SEED_FILE = Path(__file__).resolve().parent.parent / "data" / "seed_examples.json"
SEED_NAMESPACE = UUID("7542e281-cecc-4222-b247-e178a6f99319")


async def seed_examples(store: Store) -> int:
    examples = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    inserted = 0
    for example in examples:
        agents = validate_panel({"agents": example["agents"]}, 4)
        discussion_id = str(uuid5(SEED_NAMESPACE, example["key"]))
        if await store.insert_seed_discussion(discussion_id, example["topic"], agents):
            inserted += 1
    return inserted
