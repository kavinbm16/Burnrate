import csv
import json

from backend.metrics_store import MetricsStore, SessionRecord


class ReportExporter:
    def __init__(self, store: MetricsStore):
        self._store = store

    async def export_sessions_csv(self, path: str) -> None:
        sessions = await self._store.list_sessions()
        fieldnames = [
            "session_id", "mode", "scenario_name", "tools_enabled", "headroom_enabled",
            "duration_seconds", "total_cost_usd", "created_at",
        ]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for s in sessions:
                writer.writerow({
                    "session_id": s.id,
                    "mode": s.mode,
                    "scenario_name": s.scenario_name,
                    "tools_enabled": s.tools_enabled,
                    "headroom_enabled": s.headroom_enabled,
                    "duration_seconds": s.duration_seconds,
                    "total_cost_usd": s.total_cost_usd,
                    "created_at": s.created_at,
                })

    async def export_sessions_json(self) -> str:
        sessions = await self._store.list_sessions()
        out = []
        for s in sessions:
            turns = await self._store.get_turns(s.id)
            out.append({
                "session_id": s.id,
                "mode": s.mode,
                "scenario_name": s.scenario_name,
                "tools_enabled": s.tools_enabled,
                "headroom_enabled": s.headroom_enabled,
                "duration_seconds": s.duration_seconds,
                "total_cost_usd": s.total_cost_usd,
                "created_at": s.created_at,
                "turns": [
                    {
                        "turn_index": t.turn_index,
                        "input_text_tokens": t.input_text_tokens,
                        "output_text_tokens": t.output_text_tokens,
                        "tool_call_tokens": t.tool_call_tokens,
                        "audio_duration_seconds": t.audio_duration_seconds,
                        "cost_usd": t.cost_usd,
                    }
                    for t in turns
                ],
            })
        return json.dumps({"sessions": out}, indent=2)

    async def build_comparison_matrix(self) -> list[dict]:
        sessions = await self._store.list_sessions()
        matrix = []
        for s in sessions:
            turns = await self._store.get_turns(s.id)
            total_input_text = sum(t.input_text_tokens for t in turns)
            total_output_text = sum(t.output_text_tokens for t in turns)
            total_tool_tokens = sum(t.tool_call_tokens for t in turns)
            matrix.append({
                "session_id": s.id,
                "scenario_name": s.scenario_name,
                "tools_enabled": s.tools_enabled,
                "headroom_enabled": s.headroom_enabled,
                "duration_seconds": s.duration_seconds,
                "total_cost_usd": s.total_cost_usd,
                "total_input_text_tokens": total_input_text,
                "total_output_text_tokens": total_output_text,
                "total_tool_tokens": total_tool_tokens,
                "cost_per_hour_usd": (s.total_cost_usd / s.duration_seconds * 3600) if s.duration_seconds > 0 else 0,
            })
        return matrix
