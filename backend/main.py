# backend/main.py
import asyncio
import json
import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.genai import types as gtypes

from backend.config import load_config
from backend.cost_calculator import calculate_turn_cost, extrapolate_cost
from backend.gemini_errors import format_gemini_connect_error
from backend.gemini_wrapper import GeminiWrapper, GeminiSession
from backend.mcp_loader import MCPLoader
from backend.metrics_store import MetricsStore, TurnRecord
from backend.report_exporter import ReportExporter
from backend.sim_runner import SimRunner, SimConfig

# PCM byte rates used to derive audio durations from streamed bytes
INPUT_BYTES_PER_SEC = 16_000 * 2   # 16 kHz, 16-bit mono mic input
OUTPUT_BYTES_PER_SEC = 24_000 * 2  # 24 kHz, 16-bit mono model output

SCENARIOS_DIR = Path("scenarios")
FRONTEND_DIST = Path("frontend/dist")

# ── App state ──────────────────────────────────────────────────────────────
config = load_config()
store = MetricsStore()
wrapper = GeminiWrapper(config, store)
sim_runner = SimRunner(wrapper, store)
exporter = ReportExporter(store)
mcp_loader = MCPLoader(config.mcp_servers)

_sim_runs: dict[str, dict] = {}  # run_id → {status, session_id, progress, total, error}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.init()
    yield


app = FastAPI(lifespan=lifespan)


# ── REST: Config ────────────────────────────────────────────────────────────
@app.get("/api/health/gemini")
async def gemini_health():
    """Preflight: DNS + Live API WebSocket. Returns ok or a actionable error."""
    try:
        await wrapper.check_live_connectivity()
        return {"status": "ok", "model": config.gemini.model}
    except Exception as e:
        return {"status": "error", "message": str(e), "model": config.gemini.model}


@app.get("/api/config")
async def get_config():
    return {
        "model": config.gemini.model,
        "api_key_configured": bool(config.gemini.api_key),
        "pricing": {
            "audio_input_per_min": config.pricing.audio_input_per_min,
            "audio_output_per_min": config.pricing.audio_output_per_min,
            "text_input_per_mtok": config.pricing.text_input_per_mtok,
            "text_output_per_mtok": config.pricing.text_output_per_mtok,
        },
        "mcp_servers": [{"name": s.name, "type": s.type} for s in config.mcp_servers],
    }


# ── REST: Scenarios ─────────────────────────────────────────────────────────
@app.get("/api/scenarios")
async def list_scenarios():
    scenarios = []
    if SCENARIOS_DIR.is_dir():
        for path in sorted(SCENARIOS_DIR.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                turns = data.get("turns", [])
                repeat = data.get("repeat", 1)
                avg_dur = data.get("avg_turn_duration_sec", 25)
                scenarios.append({
                    "path": str(path),
                    "name": data.get("name", path.stem),
                    "description": data.get("description", ""),
                    "turn_count": len(turns) * repeat,
                    "avg_turn_duration_sec": avg_dur,
                    "repeat": repeat,
                    "estimated_duration_sec": len(turns) * repeat * avg_dur,
                    "turns": turns,
                })
            except Exception as e:
                scenarios.append({"path": str(path), "name": path.stem, "error": str(e)})
    return scenarios


# ── REST: Sessions ──────────────────────────────────────────────────────────
@app.get("/api/sessions")
async def list_sessions():
    sessions = await store.list_sessions()
    return [s.__dict__ for s in sessions]


@app.get("/api/sessions/{session_id}/turns")
async def get_turns(session_id: str):
    turns = await store.get_turns(session_id)
    return [t.__dict__ for t in turns]


@app.get("/api/sessions/{session_id}/projection")
async def get_projection(session_id: str, hours_per_day: float = 8.0, robots: int = 1):
    try:
        session = await store.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    day_sec = hours_per_day * 3600
    per_day = extrapolate_cost(session.total_cost_usd, session.duration_seconds, day_sec)
    return {
        "session_id": session_id,
        "session_cost_usd": session.total_cost_usd,
        "session_duration_seconds": session.duration_seconds,
        "hours_per_day": hours_per_day,
        "robots": robots,
        "per_hour_usd": extrapolate_cost(session.total_cost_usd, session.duration_seconds, 3600),
        "per_day_usd": per_day,
        "per_month_usd": per_day * 30,
        "fleet_per_day_usd": per_day * robots,
        "fleet_per_month_usd": per_day * 30 * robots,
    }


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    deleted = await store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": session_id}


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

    if not Path(scenario_path).is_file():
        raise HTTPException(status_code=400, detail=f"Scenario not found: {scenario_path}")

    try:
        await wrapper.check_live_connectivity()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    tool_defs = []
    if tools_enabled:
        tool_defs = await mcp_loader.load_tool_definitions()

    sim_config = SimConfig(
        scenario_path=scenario_path,
        tools_enabled=tools_enabled,
        headroom_enabled=headroom_enabled,
        tool_definitions=tool_defs,
    )

    _sim_runs[run_id] = {"status": "running", "progress": 0, "total": 0, "session_id": None, "error": None}

    async def _run():
        def on_progress(current: int, total: int):
            _sim_runs[run_id]["progress"] = current
            _sim_runs[run_id]["total"] = total

        def on_session_id(session_id: str):
            _sim_runs[run_id]["session_id"] = session_id

        try:
            result = await sim_runner.run(sim_config, on_progress=on_progress, on_session_id=on_session_id)
            _sim_runs[run_id]["status"] = "done"
            _sim_runs[run_id]["session_id"] = result.session_id
            _sim_runs[run_id]["total_cost_usd"] = result.total_cost_usd
        except Exception as e:
            _sim_runs[run_id]["status"] = "error"
            _sim_runs[run_id]["error"] = format_gemini_connect_error(e)

    asyncio.create_task(_run())
    return {"run_id": run_id}


@app.get("/api/sim/status/{run_id}")
async def sim_status(run_id: str):
    return _sim_runs.get(run_id, {"status": "not_found"})


# ── REST: Export ────────────────────────────────────────────────────────────
@app.get("/api/export/csv")
async def export_csv():
    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, "cc_bench_export.csv")
    await exporter.export_sessions_csv(tmp_path)
    return FileResponse(tmp_path, media_type="text/csv", filename="cc_token_benchmark.csv")


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

    # Mutable counters shared between the sender loop and the receive task.
    state = {
        "input_bytes": 0,    # mic bytes since last usage event
        "output_bytes": 0,   # model audio bytes since last usage event
        "total_cost": 0.0,
        "turn_index": 0,
    }

    async def record_live_turn(usage) -> dict:
        audio_in_sec = state["input_bytes"] / INPUT_BYTES_PER_SEC
        audio_out_sec = state["output_bytes"] / OUTPUT_BYTES_PER_SEC
        state["input_bytes"] = 0
        state["output_bytes"] = 0

        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0

        # Gemini Live charges separately for audio duration and tokens.
        # prompt_token_count = input tokens (audio encoded + text + system)
        # candidates_token_count = output tokens
        cost = calculate_turn_cost(
            config.pricing,
            input_text_tokens=input_tokens,
            output_text_tokens=output_tokens,
            tool_call_tokens=0,
            audio_input_duration_sec=audio_in_sec,
            audio_output_duration_sec=audio_out_sec,
        )
        state["total_cost"] += cost.total_usd

        await store.insert_turn(TurnRecord(
            session_id=session_id,
            turn_index=state["turn_index"],
            input_audio_tokens=input_tokens,
            input_text_tokens=0,
            output_audio_tokens=output_tokens,
            output_text_tokens=0,
            tool_call_tokens=0,
            audio_duration_seconds=audio_in_sec + audio_out_sec,
            cost_usd=cost.total_usd,
        ))
        state["turn_index"] += 1

        elapsed_sec = gemini_session.elapsed_seconds()
        cost_rate_per_hour = (state["total_cost"] / elapsed_sec * 3600) if elapsed_sec > 0 else 0
        return {
            "type": "metrics",
            "turn_index": state["turn_index"] - 1,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "audio_input_sec": round(audio_in_sec, 2),
            "audio_output_sec": round(audio_out_sec, 2),
            "cost_usd": cost.total_usd,
            "cost_breakdown": {
                "audio_input_usd": round(cost.audio_input_usd, 6),
                "audio_output_usd": round(cost.audio_output_usd, 6),
                "text_input_usd": round(cost.text_input_usd, 6),
                "text_output_usd": round(cost.text_output_usd, 6),
            },
            "total_cost_usd": round(state["total_cost"], 6),
            "cost_rate_per_hour_usd": round(cost_rate_per_hour, 4),
            "elapsed_seconds": round(elapsed_sec, 1),
        }

    receive_task = None
    send_task = None
    try:
        async with wrapper.client.aio.live.connect(model=wrapper.model, config=live_config) as live_session:
            await websocket.send_json({"type": "session_started", "session_id": session_id})

            async def receive_from_gemini():
                async for msg in live_session.receive():
                    if msg.server_content and msg.server_content.model_turn:
                        for part in msg.server_content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                state["output_bytes"] += len(part.inline_data.data)
                                await websocket.send_bytes(part.inline_data.data)
                    if msg.usage_metadata:
                        metrics = await record_live_turn(msg.usage_metadata)
                        await websocket.send_json(metrics)

            async def send_to_gemini():
                while True:
                    data = await websocket.receive_bytes()
                    state["input_bytes"] += len(data)
                    await live_session.send(
                        input=gtypes.Part(
                            inline_data=gtypes.Blob(data=data, mime_type="audio/pcm;rate=16000")
                        ),
                        end_of_turn=False,
                    )

            receive_task = asyncio.create_task(receive_from_gemini())
            send_task = asyncio.create_task(send_to_gemini())

            done, pending = await asyncio.wait(
                [receive_task, send_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                task.result()

    except WebSocketDisconnect:
        pass
    except (OSError, Exception) as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": format_gemini_connect_error(e),
            })
        except Exception:
            pass
    finally:
        if receive_task and not receive_task.done():
            receive_task.cancel()
        if send_task and not send_task.done():
            send_task.cancel()
        elapsed = gemini_session.elapsed_seconds()
        await store.finalize_session(session_id, elapsed, state["total_cost"])


# ── Static frontend (built SPA in frontend/dist) ────────────────────────────
if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    async def root():
        return JSONResponse({
            "app": "burnrate",
            "detail": "Frontend not built. Run `npm run build` in frontend/, or use the Vite dev server.",
        })
