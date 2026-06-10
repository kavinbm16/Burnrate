import pytest
from unittest.mock import MagicMock
from backend.sim_runner import SimRunner, SimConfig


@pytest.mark.asyncio
async def test_load_scenario():
    runner = SimRunner(wrapper=MagicMock(), store=MagicMock())
    scenario = runner.load_scenario("scenarios/typical_workday.yaml")
    assert scenario["name"] == "typical_workday"
    assert len(scenario["turns"]) > 0
    assert "avg_turn_duration_sec" in scenario


@pytest.mark.asyncio
async def test_sim_config_defaults():
    config = SimConfig(
        scenario_path="scenarios/typical_workday.yaml",
        tools_enabled=False,
        headroom_enabled=False,
    )
    assert config.tools_enabled is False
    assert config.headroom_enabled is False
