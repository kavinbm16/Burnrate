import asyncio
from dataclasses import dataclass, field
from typing import Callable

import yaml

from backend.gemini_wrapper import GeminiWrapper, GeminiSession, TurnMetrics
from backend.metrics_store import MetricsStore


@dataclass
class SimConfig:
    scenario_path: str
    tools_enabled: bool
    headroom_enabled: bool
    tool_definitions: list[dict] = field(default_factory=list)


@dataclass
class SimResult:
    session_id: str
    total_turns: int
    total_cost_usd: float
    duration_seconds: float


class SimRunner:
    def __init__(self, wrapper: GeminiWrapper, store: MetricsStore):
        self._wrapper = wrapper
        self._store = store

    def load_scenario(self, path: str) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)

    async def run(
        self,
        config: SimConfig,
        on_metrics: Callable[[TurnMetrics], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> SimResult:
        scenario = self.load_scenario(config.scenario_path)
        turns = scenario["turns"] * scenario.get("repeat", 1)
        avg_dur = scenario.get("avg_turn_duration_sec", 25)

        session_id = await self._store.create_session(
            mode="sim",
            scenario_name=scenario["name"],
            tools_enabled=config.tools_enabled,
            headroom_enabled=config.headroom_enabled,
        )
        if on_session_id:
            on_session_id(session_id)

        gemini_session = GeminiSession(
            session_id=session_id,
            tools_enabled=config.tools_enabled,
            headroom_enabled=config.headroom_enabled,
            tool_definitions=config.tool_definitions,
        )

        live_config = await self._wrapper.create_live_connect_config_for_sim(gemini_session)
        total_cost = 0.0

        async with self._wrapper.client.aio.live.connect(
            model=self._wrapper.model, config=live_config
        ) as live_session:
            for i, turn_text in enumerate(turns):
                metrics_list: list[TurnMetrics] = []

                def capture(m: TurnMetrics, _store=metrics_list):
                    _store.append(m)
                    if on_metrics:
                        on_metrics(m)

                await self._wrapper.run_sim_turn(gemini_session, turn_text, live_session, capture)

                if metrics_list:
                    total_cost += metrics_list[-1].cost_usd

                if on_progress:
                    on_progress(i + 1, len(turns))

        duration = len(turns) * avg_dur
        await self._store.finalize_session(session_id, duration_seconds=float(duration), total_cost_usd=total_cost)

        return SimResult(
            session_id=session_id,
            total_turns=len(turns),
            total_cost_usd=total_cost,
            duration_seconds=float(duration),
        )
