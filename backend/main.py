# backend/main.py
import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.genai import types as gtypes

from backend.config import load_config
from backend.cost_calculator import calculate_turn_cost
from backend.gemini_wrapper import GeminiWrapper, GeminiSession
from backend.mcp_loader import MCPLoader
from backend.metrics_store import MetricsStore
from backend.report_exporter import ReportExporter
from backend.sim_runner import SimRunner, SimConfig


# ── App state ──────────────────────────────────────────────────────────────
config = load_config()
store = MetricsStore()
wrapper = GeminiWrapper(config, store)
sim_runner = SimRunner(wrapper, store)
exporter = ReportExporter(store)
mcp_loader = MCPLoader(config.mcp_servers)

_sim_runs: dict[str, dict] = {}  # run_id → {status, session_id, progress}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


# ── REST: Sessions ──────────────────────────────────────────────────────────
@app.get("/api/sessions")
async def list_sessions():
    sessions = await store.list_sessions()
    return [s.__dict__ for s in sessions]


@app.get("/api/sessions/{session_id}/turns")
async def get_turns(session_id: str):
    turns = await store.get_turns(session_id)
    return [t.__dict__ for t in turns]


@app.get("/api/comparison")
async def get_comparison():
    matrix = await exporter.build_comparison_matrix()
    return matrix


# ── REST: Sim ───────────────────────────────────────────────────────────────
@app.post("/api/sim/run")
async def start_sim(body: dict):
    run_id = str(uuid.uuid4())
    scenario_path = body.get("scenario_path", "scenarios/typical_workday.yaml")
    tools_enabled = body.get("tools_enabled", False)
    headroom_enabled = body.get("headroom_enabled", False)

    tool_defs = []
    if tools_enabled:
        tool_defs = await mcp_loader.load_tool_definitions()

    sim_config = SimConfig(
        scenario_path=scenario_path,
        tools_enabled=tools_enabled,
        headroom_enabled=headroom_enabled,
        tool_definitions=tool_defs,
    )

    _sim_runs[run_id] = {"status": "running", "progress": 0, "total": 0, "session_id": None}

    async def _run():
        def on_progress(current: int, total: int):
            _sim_runs[run_id]["progress"] = current
            _sim_runs[run_id]["total"] = total

        result = await sim_runner.run(sim_config, on_progress=on_progress)
        _sim_runs[run_id]["status"] = "done"
        _sim_runs[run_id]["session_id"] = result.session_id

    asyncio.create_task(_run())
    return {"run_id": run_id}


@app.get("/api/sim/status/{run_id}")
async def sim_status(run_id: str):
    return _sim_runs.get(run_id, {"status": "not_found"})


# ── REST: Export ────────────────────────────────────────────────────────────
@app.get("/api/export/csv")
async def export_csv():
    tmp_path = "/tmp/burnrate_export.csv"
    await exporter.export_sessions_csv(tmp_path)
    return FileResponse(tmp_path, media_type="text/csv", filename="burnrate_export.csv")


@app.get("/api/export/json")
async def export_json():
    data = await exporter.export_sessions_json()
    return JSONResponse(content=json.loads(data))


# ── WebSocket: Live audio mode ──────────────────────────────────────────────
@app.websocket("/ws/live")
async def live_audio(websocket: WebSocket):
    await websocket.accept()
    tools_enabled = False
    headroom_enabled = False

    try:
        init_msg = await websocket.receive_json()
        tools_enabled = init_msg.get("tools_enabled", False)
        headroom_enabled = init_msg.get("headroom_enabled", False)
    except Exception:
        pass

    tool_defs = []
    if tools_enabled:
        tool_defs = await mcp_loader.load_tool_definitions()

    session_id = await store.create_session("live", "live_session", tools_enabled, headroom_enabled)
    gemini_session = GeminiSession(
        session_id=session_id,
        tools_enabled=tools_enabled,
        headroom_enabled=headroom_enabled,
        tool_definitions=tool_defs,
    )

    live_config = await wrapper.create_live_connect_config_for_audio(gemini_session)
    await websocket.send_json({"type": "session_started", "session_id": session_id})

    receive_task = None
    try:
        async with wrapper.client.aio.live.connect(model=wrapper.model, config=live_config) as live_session:
            async def receive_from_gemini():
                async for msg in live_session.receive():
                    if msg.server_content and msg.server_content.model_turn:
                        for part in msg.server_content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                await websocket.send_bytes(part.inline_data.data)
                    if msg.usage_metadata:
                        usage = msg.usage_metadata
                        cost = calculate_turn_cost(
                            config.pricing,
                            input_text_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                            output_text_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                            tool_call_tokens=0,
                            audio_input_duration_sec=0,
                            audio_output_duration_sec=0,
                        )
                        await websocket.send_json({
                            "type": "metrics",
                            "input_tokens": getattr(usage, "prompt_token_count", 0),
                            "output_tokens": getattr(usage, "candidates_token_count", 0),
                            "cost_usd": cost.total_usd,
                        })

            receive_task = asyncio.create_task(receive_from_gemini())

            while True:
                data = await websocket.receive_bytes()
                await live_session.send(
                    input=gtypes.Part(
                        inline_data=gtypes.Blob(data=data, mime_type="audio/pcm;rate=16000")
                    ),
                    end_of_turn=False,
                )

    except WebSocketDisconnect:
        pass
    finally:
        if receive_task:
            receive_task.cancel()
        session = await store.get_session(session_id)
        elapsed = gemini_session.elapsed_seconds()
        await store.finalize_session(session_id, elapsed, session.total_cost_usd)


# ── Root: serve dashboard ───────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("frontend/index.html")
