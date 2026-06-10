import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GeminiConfig:
    api_key: str
    model: str


@dataclass
class PricingConfig:
    audio_input_per_min: float
    audio_output_per_min: float
    text_input_per_mtok: float
    text_output_per_mtok: float


@dataclass
class MCPServerConfig:
    name: str
    type: str          # "http" or "stdio"
    url: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    gemini: GeminiConfig
    pricing: PricingConfig
    mcp_servers: list[MCPServerConfig]


def load_config(path: str = "mcp.toml") -> AppConfig:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    gemini = GeminiConfig(**raw["gemini"])
    pricing = PricingConfig(**raw["pricing"])
    servers = [
        MCPServerConfig(name=name, **cfg)
        for name, cfg in raw.get("mcp_servers", {}).items()
    ]
    return AppConfig(gemini=gemini, pricing=pricing, mcp_servers=servers)
