# backend/gemini_wrapper.py
import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

import google.genai as genai
from google.genai import types as gtypes

from backend.config import AppConfig
from backend.system_instruction import SYSTEM_INSTRUCTION
from backend.cost_calculator import calculate_turn_cost
from backend.gemini_errors import check_dns, format_gemini_connect_error
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
    history: list[dict] = field(default_factory=list)  # OpenAI-format messages for headroom
    tokens_saved_by_headroom: int = 0
    _turn_index: int = 0
    _session_start: float = field(default_factory=time.time)

    def elapsed_seconds(self) -> float:
        return time.time() - self._session_start


class GeminiWrapper:
    def __init__(self, config: AppConfig, store: MetricsStore):
        self._config = config
        self._store = store
        if not config.gemini.api_key:
            raise ValueError("GEMINI_API is not set — add it to .env")
        self._client = genai.Client(api_key=config.gemini.api_key)

    async def check_live_connectivity(self, timeout: float = 20.0) -> None:
        """Verify DNS + Gemini Live WebSocket before starting a sim or live session."""
        check_dns()
        probe = GeminiSession(
            session_id="probe",
            tools_enabled=False,
            headroom_enabled=False,
        )
        cfg = await self.create_live_connect_config_for_sim(probe)
        try:
            async with asyncio.timeout(timeout):
                async with self._client.aio.live.connect(model=self.model, config=cfg):
                    pass
        except Exception as e:
            raise RuntimeError(format_gemini_connect_error(e)) from e

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
            system_instruction=gtypes.Content(parts=[gtypes.Part(text=SYSTEM_INSTRUCTION)]),
        )

    def _compress_if_enabled(self, session: GeminiSession, messages: list[dict]) -> list[dict]:
        """Compress conversation messages via headroom-ai before sending.

        Returns the (possibly compressed) message list and accumulates token
        savings on the session. Falls back to the original messages if the
        library is unavailable or compression fails.
        """
        if not session.headroom_enabled:
            return messages
        try:
            from headroom import compress

            result = compress(messages)
            session.tokens_saved_by_headroom += result.tokens_saved
            if result.tokens_saved > 0:
                print(
                    f"[GeminiWrapper] headroom: {result.tokens_before} → {result.tokens_after} tokens "
                    f"(saved {result.tokens_saved}, transforms: {result.transforms_applied})"
                )
            return result.messages
        except ImportError:
            print("[GeminiWrapper] headroom-ai not installed, skipping compression")
            return messages
        except Exception as e:
            print(f"[GeminiWrapper] headroom compression failed, sending uncompressed: {e}")
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
        audio_input_sec: float = 0.0,
        audio_output_sec: float = 0.0,
    ) -> str:
        """Send one text turn, collect response, record metrics.

        With headroom enabled, the running conversation history is compressed
        before each send and the compressed form of the new user turn is what
        goes over the wire. (Gemini Live keeps its own server-side context;
        compression reduces the client-supplied content per turn — the same
        place tool outputs and injected context would be compressed in CC.)
        """
        session.history.append({"role": "user", "content": text})
        outgoing = text
        if session.headroom_enabled:
            compressed = self._compress_if_enabled(session, session.history)
            session.history = list(compressed)
            last = session.history[-1] if session.history else None
            if last and last.get("role") == "user" and isinstance(last.get("content"), str):
                outgoing = last["content"]

        await live_session.send(input=outgoing, end_of_turn=True)

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

        session.history.append({"role": "assistant", "content": response_text})
        await self._record_turn(session, usage, audio_input_sec, audio_output_sec, on_metrics)
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
