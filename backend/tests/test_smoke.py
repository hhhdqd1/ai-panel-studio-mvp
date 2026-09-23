from __future__ import annotations

import pytest

from app.fake_gateway import FakeGateway
from app.smoke import run_smoke


@pytest.mark.asyncio
async def test_smoke_runs_complete_fake_discussion_in_isolated_database(tmp_path):
    result = await run_smoke(
        tmp_path / "smoke.sqlite3", FakeGateway(), "教育与人工智能？", 2
    )
    assert result["status"] == "completed"
    assert result["panel_size"] == 3
    assert result["expert_turns"] >= 12
    assert result["flags"] >= 1
    assert "待核实" in result["summary"]
    assert result["model_runs"] > 0
