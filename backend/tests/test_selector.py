from __future__ import annotations

from app.selector import select_speaker


def intent(agent_id: str, **changes) -> dict:
    value = {
        "agent_id": agent_id,
        "wants_to_speak": True,
        "action": "answer",
        "target_message_id": None,
        "relevance": 0.7,
        "novelty": 0.5,
        "urgency": 0.5,
        "public_intent": "准备补充案例",
    }
    value.update(changes)
    return value


def test_not_round_robin_and_order_independent():
    intents = [
        intent("a", relevance=0.6, novelty=0.4, urgency=0.4),
        intent("b", action="challenge", target_message_id="m1", relevance=0.9, novelty=0.9, urgency=0.8),
    ]
    assert select_speaker(intents, ["a"], {"a": 2, "b": 0})["agent_id"] == "b"
    assert select_speaker(list(reversed(intents)), ["a"], {"a": 2, "b": 0})["agent_id"] == "b"


def test_recent_speaker_is_penalized_when_interest_is_equal():
    selected = select_speaker([intent("a"), intent("b")], ["a"], {"a": 1, "b": 1})
    assert selected["agent_id"] == "b"


def test_targeted_challenge_can_win_when_other_scores_are_close():
    selected = select_speaker(
        [intent("a", relevance=0.75), intent("b", action="challenge", target_message_id="m7")],
        [],
        {"a": 1, "b": 1},
    )
    assert selected["agent_id"] == "b"


def test_everyone_declines():
    assert select_speaker([], [], {}) is None
    assert select_speaker([intent("a", wants_to_speak=False)], [], {}) is None


def test_ties_are_stable_and_not_input_order_dependent():
    assert select_speaker([intent("z"), intent("a")], [], {})["agent_id"] == "a"
    assert select_speaker([intent("a"), intent("z")], [], {})["agent_id"] == "a"


def test_private_fields_are_not_returned_to_the_event_layer():
    selected = select_speaker(
        [intent("a", private_reasoning="hidden", chain_of_thought="hidden")], [], {}
    )
    assert selected["public_intent"] == "准备补充案例"
    assert "private_reasoning" not in selected
    assert "chain_of_thought" not in selected


def test_invalid_scores_are_clamped_or_zeroed():
    selected = select_speaker(
        [intent("a", relevance="not a number", novelty=-5, urgency=0), intent("b", relevance=2, novelty=2, urgency=2)],
        [],
        {},
    )
    assert selected["agent_id"] == "b"
