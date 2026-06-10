import pytest
import json
from backend.metrics_store import MetricsStore, TurnRecord
from backend.report_exporter import ReportExporter
from backend.config import PricingConfig


@pytest.fixture
async def populated_store(tmp_path):
    store = MetricsStore(str(tmp_path / "test.db"))
    await store.init()
    s1 = await store.create_session("sim", "workday", True, False)
    await store.insert_turn(TurnRecord(s1, 0, 0, 200, 0, 100, 10, 25.0, 0.002))
    await store.insert_turn(TurnRecord(s1, 1, 0, 180, 0, 90, 0, 22.0, 0.0015))
    await store.finalize_session(s1, 47.0, 0.0035)
    s2 = await store.create_session("sim", "workday", True, True)
    await store.insert_turn(TurnRecord(s2, 0, 0, 80, 0, 40, 5, 25.0, 0.0008))
    await store.finalize_session(s2, 25.0, 0.0008)
    return store, s1, s2


@pytest.mark.asyncio
async def test_export_csv_has_correct_columns(populated_store, tmp_path):
    store, s1, _ = populated_store
    exporter = ReportExporter(store)
    csv_path = str(tmp_path / "out.csv")
    await exporter.export_sessions_csv(csv_path)

    with open(csv_path) as f:
        lines = f.readlines()

    assert "session_id" in lines[0]
    assert "total_cost_usd" in lines[0]
    assert "tools_enabled" in lines[0]
    assert len(lines) == 3  # header + 2 sessions


@pytest.mark.asyncio
async def test_export_json_structure(populated_store, tmp_path):
    store, s1, s2 = populated_store
    exporter = ReportExporter(store)
    data = await exporter.export_sessions_json()
    parsed = json.loads(data)
    assert len(parsed["sessions"]) == 2
    assert "turns" in parsed["sessions"][0]


@pytest.mark.asyncio
async def test_comparison_matrix(populated_store):
    store, s1, s2 = populated_store
    exporter = ReportExporter(store)
    matrix = await exporter.build_comparison_matrix()
    assert len(matrix) == 2
    assert all("session_id" in row for row in matrix)
    assert all("total_cost_usd" in row for row in matrix)
