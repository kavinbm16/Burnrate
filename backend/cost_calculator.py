# backend/cost_calculator.py
from dataclasses import dataclass
from backend.config import PricingConfig


@dataclass
class TurnCost:
    audio_input_usd: float
    audio_output_usd: float
    text_input_usd: float
    text_output_usd: float
    total_usd: float


def calculate_turn_cost(
    pricing: PricingConfig,
    input_text_tokens: int,
    output_text_tokens: int,
    tool_call_tokens: int,
    audio_input_duration_sec: float,
    audio_output_duration_sec: float,
) -> TurnCost:
    audio_input_usd = (audio_input_duration_sec / 60.0) * pricing.audio_input_per_min
    audio_output_usd = (audio_output_duration_sec / 60.0) * pricing.audio_output_per_min
    total_text_input = input_text_tokens + tool_call_tokens
    text_input_usd = (total_text_input / 1_000_000) * pricing.text_input_per_mtok
    text_output_usd = (output_text_tokens / 1_000_000) * pricing.text_output_per_mtok
    total_usd = audio_input_usd + audio_output_usd + text_input_usd + text_output_usd
    return TurnCost(
        audio_input_usd=audio_input_usd,
        audio_output_usd=audio_output_usd,
        text_input_usd=text_input_usd,
        text_output_usd=text_output_usd,
        total_usd=total_usd,
    )


def extrapolate_cost(session_total_usd: float, session_duration_sec: float, target_duration_sec: float) -> float:
    if session_duration_sec == 0:
        return 0.0
    return session_total_usd * (target_duration_sec / session_duration_sec)
