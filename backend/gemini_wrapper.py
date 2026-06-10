# backend/gemini_wrapper.py
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

import google.genai as genai
from google.genai import types as gtypes

from backend.config import AppConfig
from backend.cost_calculator import calculate_turn_cost
from backend.metrics_store import MetricsStore, TurnRecord


@dataclass
class TurnMetrics:
    turn_index: int
    input_text_tokens: int
    output_text_tokens: int
    tool_call_tokens: int
    input_audio_tokens: int
    output_audio_tokens: int
    audio_input_duration_sec: float
    audio_output_duration_sec: float
    cost_usd: float


@dataclass
class GeminiSession:
    session_id: str
    tools_enabled: bool
    headroom_enabled: bool
    tool_definitions: list[dict] = field(default_factory=list)
    _turn_index: int = 0
    _session_start: float = field(default_factory=time.time)

    def elapsed_seconds(self) -> float:
        return time.time() - self._session_start


class GeminiWrapper:
    def __init__(self, config: AppConfig, store: MetricsStore):
        self._config = config
        self._store = store
        self._client = genai.Client(api_key=config.gemini.api_key)

    def _build_live_config(self, session: GeminiSession, response_modality: str) -> gtypes.LiveConnectConfig:
        tools = []
        if session.tools_enabled and session.tool_definitions:
            function_declarations = [
                gtypes.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=t.get("parameters"),
                )
                for t in session.tool_definitions
            ]
            tools = [gtypes.Tool(function_declarations=function_declarations)]

        return gtypes.LiveConnectConfig(
            response_modalities=[response_modality],
            tools=tools if tools else None,
        )

    def _compress_if_enabled(self, session: GeminiSession, messages: list) -> list:
        if not session.headroom_enabled:
            return messages
        try:
            from headroom import compress
            return compress(messages)
        except (ImportError, AttributeError):
            print("[GeminiWrapper] headroom compress not available, skipping compression")
            return messages

    async def _record_turn(
        self,
        session: GeminiSession,
        usage: gtypes.GenerateContentResponseUsageMetadata | None,
        audio_input_sec: float,
        audio_output_sec: float,
        on_metrics: Callable[[TurnMetrics], None] | None = None,
    ) -> None:
        input_text = getattr(usage, "prompt_token_count", 0) or 0
        output_text = getattr(usage, "candidates_token_count", 0) or 0
        tool_tokens = 0

        cost = calculate_turn_cost(
            self._config.pricing,
            input_text_tokens=input_text,
            output_text_tokens=output_text,
            tool_call_tokens=tool_tokens,
            audio_input_duration_sec=audio_input_sec,
            audio_output_duration_sec=audio_output_sec,
        )

        turn = TurnRecord(
            session_id=session.session_id,
            turn_index=session._turn_index,
            input_audio_tokens=0,
            input_text_tokens=input_text,
            output_audio_tokens=0,
            output_text_tokens=output_text,
            tool_call_tokens=tool_tokens,
            audio_duration_seconds=audio_input_sec + audio_output_sec,
            cost_usd=cost.total_usd,
        )
        await self._store.insert_turn(turn)

        if on_metrics:
            on_metrics(TurnMetrics(
                turn_index=session._turn_index,
                input_text_tokens=input_text,
                output_text_tokens=output_text,
                tool_call_tokens=tool_tokens,
                input_audio_tokens=0,
                output_audio_tokens=0,
                audio_input_duration_sec=audio_input_sec,
                audio_output_duration_sec=audio_output_sec,
                cost_usd=cost.total_usd,
            ))

        session._turn_index += 1

    async def run_sim_turn(
        self,
        session: GeminiSession,
        text: str,
        live_session: object,
        on_metrics: Callable[[TurnMetrics], None] | None = None,
    ) -> str:
        """Send one text turn, collect response, record metrics."""
        await live_session.send(input=text, end_of_turn=True)

        response_text = ""
        usage = None
        async for msg in live_session.receive():
            if msg.server_content and msg.server_content.model_turn:
                for part in msg.server_content.model_turn.parts:
                    if part.text:
                        response_text += part.text
            if msg.usage_metadata:
                usage = msg.usage_metadata
            if msg.server_content and msg.server_content.turn_complete:
                break

        await self._record_turn(session, usage, 0.0, 0.0, on_metrics)
        return response_text

    async def create_live_connect_config_for_sim(self, session: GeminiSession) -> gtypes.LiveConnectConfig:
        return self._build_live_config(session, response_modality="TEXT")

    async def create_live_connect_config_for_audio(self, session: GeminiSession) -> gtypes.LiveConnectConfig:
        return self._build_live_config(session, response_modality="AUDIO")

    @property
    def client(self) -> genai.Client:
        return self._client

    @property
    def model(self) -> str:
        return self._config.gemini.model
