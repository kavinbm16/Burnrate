import asyncio
import pytest
from backend.metrics_store import MetricsStore, SessionRecord, TurnRecord


@pytest.fixture
async def store(tmp_path):
    s = MetricsStore(str(tmp_path / "test.db"))
    await s.init()
    return s


@pytest.mark.asyncio
async def test_create_and_get_session(store):
    session_id = await store.create_session(
        mode="sim",
        scenario_name="test_scenario",
        tools_enabled=True,
        headroom_enabled=False,
    )
    assert isinstance(session_id, str) and len(session_id) == 36

    session = await store.get_session(session_id)
    assert session.mode == "sim"
    assert session.tools_enabled is True
    assert session.headroom_enabled is False


@pytest.mark.asyncio
async def test_insert_and_query_turns(store):
    session_id = await store.create_session("sim", "s", True, False)
    turn = TurnRecord(
        session_id=session_id,
        turn_index=0,
        input_audio_tokens=0,
        input_text_tokens=150,
        output_audio_tokens=0,
        output_text_tokens=80,
        tool_call_tokens=20,
        audio_duration_seconds=0.0,
        cost_usd=0.00045,
    )
    await store.insert_turn(turn)

    turns = await store.get_turns(session_id)
    assert len(turns) == 1
    assert turns[0].input_text_tokens == 150
    assert turns[0].cost_usd == pytest.approx(0.00045)


@pytest.mark.asyncio
async def test_finalize_session(store):
    session_id = await store.create_session("sim", "s", False, False)
    await store.finalize_session(session_id, duration_seconds=120.0, total_cost_usd=0.05)
    session = await store.get_session(session_id)
    assert session.duration_seconds == 120.0
    assert session.total_cost_usd == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_list_sessions(store):
    await store.create_session("live", "none", False, False)
    await store.create_session("sim", "workday", True, True)
    sessions = await store.list_sessions()
    assert len(sessions) == 2
