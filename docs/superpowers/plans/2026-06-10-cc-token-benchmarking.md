# CC Token Benchmarking Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python + web dashboard tool to benchmark Gemini 3.1 Flash Live token costs for the CC robot across all variable axes (tools on/off, headroom on/off, session duration).

**Architecture:** FastAPI backend wraps the Gemini Live SDK, captures `usageMetadata` per turn, and stores results in SQLite. A browser UI provides live audio conversation mode, a scriptable sim runner, and a cost analytics/comparison dashboard.

**Tech Stack:** Python 3.11+, FastAPI, `google-genai` SDK, `headroom` library, `mcp` Python SDK, SQLite via `aiosqlite`, Chart.js, vanilla HTML/JS

---

## File Map

```
token-usage/
├── mcp.toml                          ← API keys, pricing, MCP server configs
├── scenarios/
│   └── typical_workday.yaml          ← example scenario script
├── backend/
│   ├── config.py                     ← load + validate mcp.toml
│   ├── metrics_store.py              ← SQLite: sessions + turns schema + queries
│   ├── mcp_loader.py                 ← connect to MCP servers, return tool definitions
│   ├── gemini_wrapper.py             ← Gemini Live session, usageMetadata capture
│   ├── sim_runner.py                 ← replay YAML scenario via GeminiWrapper
│   ├── report_exporter.py           ← CSV + JSON export from MetricsStore
│   └── main.py                       ← FastAPI app: REST routes + WebSocket
├── frontend/
│   ├── index.html                    ← tab shell
│   ├── app.js                        ← tab routing, WebSocket, Chart.js
│   └── style.css
├── tests/
│   ├── test_metrics_store.py
│   ├── test_sim_runner.py
│   ├── test_mcp_loader.py
│   └── test_report_exporter.py
└── requirements.txt
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `mcp.toml`
- Create: `scenarios/typical_workday.yaml`
- Create: `backend/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
google-genai==1.0.0
aiosqlite==0.20.0
tomli==2.0.1
pyyaml==6.0.2
mcp==1.0.0
headroom==0.1.0
pytest==8.3.0
pytest-asyncio==0.23.8
httpx==0.27.0
```

- [ ] **Step 2: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: no errors. Verify with `python -c "import google.genai; import fastapi; import aiosqlite"`.

- [ ] **Step 3: Create mcp.toml**

```toml
[gemini]
api_key = "YOUR_GEMINI_API_KEY"
model   = "gemini-3.1-flash-live-preview"

[pricing]
audio_input_per_min   = 0.005
audio_output_per_min  = 0.018
text_input_per_mtok   = 0.75
text_output_per_mtok  = 4.50

# Add your MCP servers below. Supports type = "http" or "stdio".
# [mcp_servers.filesystem]
# type    = "stdio"
# command = "npx"
# args    = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

# [mcp_servers.my_api]
# type = "http"
# url  = "http://localhost:3001"
```

- [ ] **Step 4: Create scenarios/typical_workday.yaml**

```yaml
name: typical_workday
description: "Simulates a typical 30-minute robot interaction"
avg_turn_duration_sec: 25
system_prompt: "You are CC, a helpful desktop robot assistant."
turns:
  - "Good morning! What's the weather like today?"
  - "Set a reminder for my 3pm meeting."
  - "Play some background music."
  - "What did I have scheduled for yesterday?"
  - "Send a message to the team saying I'll be 5 minutes late."
  - "Turn off the lights in the conference room."
  - "What is the capital of France?"
  - "Order lunch from the usual place."
  - "Read out my unread emails."
  - "How many steps have I taken today?"
repeat: 1
```

- [ ] **Step 5: Create empty init files**

```bash
mkdir -p backend tests frontend scenarios
touch backend/__init__.py tests/__init__.py
```

- [ ] **Step 6: Commit**

```bash
git init
git add .
git commit -m "feat: project scaffold, config, and example scenario"
```

---

## Task 2: Config Loader

**Files:**
- Create: `backend/config.py`

- [ ] **Step 1: Create backend/config.py**

```python
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
```

- [ ] **Step 2: Verify manually**

```bash
python -c "from backend.config import load_config; c = load_config(); print(c.pricing)"
```

Expected: `PricingConfig(audio_input_per_min=0.005, ...)` printed.

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat: config loader for mcp.toml"
```

---

## Task 3: MetricsStore

**Files:**
- Create: `backend/metrics_store.py`
- Create: `tests/test_metrics_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_metrics_store.py
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
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_metrics_store.py -v
```

Expected: `ImportError: cannot import name 'MetricsStore'`

- [ ] **Step 3: Implement MetricsStore**

```python
# backend/metrics_store.py
import uuid
from dataclasses import dataclass
from datetime import datetime

import aiosqlite


@dataclass
class SessionRecord:
    id: str
    mode: str
    scenario_name: str
    tools_enabled: bool
    headroom_enabled: bool
    created_at: str = ""
    duration_seconds: float = 0.0
    total_cost_usd: float = 0.0


@dataclass
class TurnRecord:
    session_id: str
    turn_index: int
    input_audio_tokens: int
    input_text_tokens: int
    output_audio_tokens: int
    output_text_tokens: int
    tool_call_tokens: int
    audio_duration_seconds: float
    cost_usd: float


class MetricsStore:
    def __init__(self, db_path: str = "metrics.db"):
        self._path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    scenario_name TEXT,
                    tools_enabled INTEGER NOT NULL,
                    headroom_enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    duration_seconds REAL DEFAULT 0,
                    total_cost_usd REAL DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    input_audio_tokens INTEGER DEFAULT 0,
                    input_text_tokens INTEGER DEFAULT 0,
                    output_audio_tokens INTEGER DEFAULT 0,
                    output_text_tokens INTEGER DEFAULT 0,
                    tool_call_tokens INTEGER DEFAULT 0,
                    audio_duration_seconds REAL DEFAULT 0,
                    cost_usd REAL DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            await db.commit()

    async def create_session(
        self,
        mode: str,
        scenario_name: str,
        tools_enabled: bool,
        headroom_enabled: bool,
    ) -> str:
        session_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO sessions (id, mode, scenario_name, tools_enabled, headroom_enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, mode, scenario_name, int(tools_enabled), int(headroom_enabled), datetime.utcnow().isoformat()),
            )
            await db.commit()
        return session_id

    async def get_session(self, session_id: str) -> SessionRecord:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cur:
                row = await cur.fetchone()
        return SessionRecord(
            id=row["id"],
            mode=row["mode"],
            scenario_name=row["scenario_name"],
            tools_enabled=bool(row["tools_enabled"]),
            headroom_enabled=bool(row["headroom_enabled"]),
            created_at=row["created_at"],
            duration_seconds=row["duration_seconds"],
            total_cost_usd=row["total_cost_usd"],
        )

    async def insert_turn(self, turn: TurnRecord) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """INSERT INTO turns
                   (session_id, turn_index, created_at, input_audio_tokens, input_text_tokens,
                    output_audio_tokens, output_text_tokens, tool_call_tokens,
                    audio_duration_seconds, cost_usd)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    turn.session_id, turn.turn_index, datetime.utcnow().isoformat(),
                    turn.input_audio_tokens, turn.input_text_tokens,
                    turn.output_audio_tokens, turn.output_text_tokens,
                    turn.tool_call_tokens, turn.audio_duration_seconds, turn.cost_usd,
                ),
            )
            await db.commit()

    async def get_turns(self, session_id: str) -> list[TurnRecord]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY turn_index", (session_id,)
            ) as cur:
                rows = await cur.fetchall()
        return [
            TurnRecord(
                session_id=r["session_id"],
                turn_index=r["turn_index"],
                input_audio_tokens=r["input_audio_tokens"],
                input_text_tokens=r["input_text_tokens"],
                output_audio_tokens=r["output_audio_tokens"],
                output_text_tokens=r["output_text_tokens"],
                tool_call_tokens=r["tool_call_tokens"],
                audio_duration_seconds=r["audio_duration_seconds"],
                cost_usd=r["cost_usd"],
            )
            for r in rows
        ]

    async def finalize_session(self, session_id: str, duration_seconds: float, total_cost_usd: float) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE sessions SET duration_seconds = ?, total_cost_usd = ? WHERE id = ?",
                (duration_seconds, total_cost_usd, session_id),
            )
            await db.commit()

    async def list_sessions(self) -> list[SessionRecord]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM sessions ORDER BY created_at DESC") as cur:
                rows = await cur.fetchall()
        return [
            SessionRecord(
                id=r["id"], mode=r["mode"], scenario_name=r["scenario_name"],
                tools_enabled=bool(r["tools_enabled"]), headroom_enabled=bool(r["headroom_enabled"]),
                created_at=r["created_at"], duration_seconds=r["duration_seconds"],
                total_cost_usd=r["total_cost_usd"],
            )
            for r in rows
        ]
```

- [ ] **Step 4: Add pytest-asyncio config to pyproject.toml**

```bash
cat >> pyproject.toml << 'EOF'
[tool.pytest.ini_options]
asyncio_mode = "auto"
EOF
```

Or create `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
pytest tests/test_metrics_store.py -v
```

Expected: 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/metrics_store.py tests/test_metrics_store.py pytest.ini
git commit -m "feat: metrics store with SQLite sessions and turns schema"
```

---

## Task 4: Cost Calculator

**Files:**
- Create: `backend/cost_calculator.py`

This is a pure function module — no I/O, no dependencies, easy to test inline.

- [ ] **Step 1: Create backend/cost_calculator.py**

```python
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
```

- [ ] **Step 2: Verify with quick test**

```bash
python -c "
from backend.config import PricingConfig
from backend.cost_calculator import calculate_turn_cost
p = PricingConfig(0.005, 0.018, 0.75, 4.50)
c = calculate_turn_cost(p, 500, 200, 100, 30.0, 20.0)
print(f'Turn cost: \${c.total_usd:.6f}')
print(f'  audio in: \${c.audio_input_usd:.6f}')
print(f'  audio out: \${c.audio_output_usd:.6f}')
"
```

Expected: numeric values printed, no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/cost_calculator.py
git commit -m "feat: cost calculator for per-turn and extrapolated pricing"
```

---

## Task 5: MCP Loader

**Files:**
- Create: `backend/mcp_loader.py`
- Create: `tests/test_mcp_loader.py`

The loader reads TOML config, connects to each MCP server, and returns tool definitions in Gemini's `Tool` format.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_mcp_loader.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.config import MCPServerConfig
from backend.mcp_loader import MCPLoader


@pytest.mark.asyncio
async def test_no_servers_returns_empty():
    loader = MCPLoader(servers=[])
    tools = await loader.load_tool_definitions()
    assert tools == []


@pytest.mark.asyncio
async def test_tool_definition_schema_shape():
    # MCPLoader converts MCP tool schemas into Gemini FunctionDeclaration dicts
    mock_tool = MagicMock()
    mock_tool.name = "search_files"
    mock_tool.description = "Search for files"
    mock_tool.inputSchema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    loader = MCPLoader(servers=[])
    result = loader._mcp_tool_to_gemini(mock_tool)

    assert result["name"] == "search_files"
    assert result["description"] == "Search for files"
    assert "parameters" in result
    assert result["parameters"]["properties"]["query"]["type"] == "string"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_mcp_loader.py -v
```

Expected: `ImportError: cannot import name 'MCPLoader'`

- [ ] **Step 3: Implement MCPLoader**

```python
# backend/mcp_loader.py
import asyncio
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from backend.config import MCPServerConfig


class MCPLoader:
    def __init__(self, servers: list[MCPServerConfig]):
        self._servers = servers

    def _mcp_tool_to_gemini(self, tool: Any) -> dict:
        return {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        }

    async def _load_from_http_server(self, server: MCPServerConfig) -> list[dict]:
        try:
            async with sse_client(server.url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [self._mcp_tool_to_gemini(t) for t in result.tools]
        except Exception as e:
            print(f"[MCPLoader] Failed to connect to {server.name} ({server.url}): {e}")
            return []

    async def _load_from_stdio_server(self, server: MCPServerConfig) -> list[dict]:
        try:
            params = StdioServerParameters(command=server.command, args=server.args)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [self._mcp_tool_to_gemini(t) for t in result.tools]
        except Exception as e:
            print(f"[MCPLoader] Failed to connect to {server.name}: {e}")
            return []

    async def load_tool_definitions(self) -> list[dict]:
        tasks = []
        for server in self._servers:
            if server.type == "http":
                tasks.append(self._load_from_http_server(server))
            elif server.type == "stdio":
                tasks.append(self._load_from_stdio_server(server))

        results = await asyncio.gather(*tasks)
        return [tool for server_tools in results for tool in server_tools]
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_mcp_loader.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_loader.py tests/test_mcp_loader.py
git commit -m "feat: MCP loader — connects to stdio/http servers, returns Gemini tool definitions"
```

---

## Task 6: Gemini Wrapper

**Files:**
- Create: `backend/gemini_wrapper.py`

This wraps the Gemini Live SDK, captures `usageMetadata` per turn, optionally compresses messages via headroom, and writes `TurnRecord`s to `MetricsStore`.

- [ ] **Step 1: Create backend/gemini_wrapper.py**

```python
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
        except ImportError:
            print("[GeminiWrapper] headroom not installed, skipping compression")
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
```

- [ ] **Step 2: Verify import**

```bash
python -c "from backend.gemini_wrapper import GeminiWrapper; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/gemini_wrapper.py
git commit -m "feat: Gemini Live wrapper with usageMetadata capture and headroom integration"
```

---

## Task 7: SimRunner

**Files:**
- Create: `backend/sim_runner.py`
- Create: `tests/test_sim_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sim_runner.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.sim_runner import SimRunner, SimConfig


@pytest.mark.asyncio
async def test_load_scenario():
    runner = SimRunner(wrapper=MagicMock(), store=MagicMock())
    scenario = runner.load_scenario("scenarios/typical_workday.yaml")
    assert scenario["name"] == "typical_workday"
    assert len(scenario["turns"]) > 0
    assert "avg_turn_duration_sec" in scenario


@pytest.mark.asyncio
async def test_sim_config_defaults():
    config = SimConfig(
        scenario_path="scenarios/typical_workday.yaml",
        tools_enabled=False,
        headroom_enabled=False,
    )
    assert config.tools_enabled is False
    assert config.headroom_enabled is False
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_sim_runner.py -v
```

Expected: `ImportError: cannot import name 'SimRunner'`

- [ ] **Step 3: Implement SimRunner**

```python
# backend/sim_runner.py
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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_sim_runner.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/sim_runner.py tests/test_sim_runner.py
git commit -m "feat: sim runner — replay YAML scenario turns via Gemini Live"
```

---

## Task 8: Report Exporter

**Files:**
- Create: `backend/report_exporter.py`
- Create: `tests/test_report_exporter.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_report_exporter.py
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
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_report_exporter.py -v
```

Expected: `ImportError: cannot import name 'ReportExporter'`

- [ ] **Step 3: Implement ReportExporter**

```python
# backend/report_exporter.py
import csv
import json
from io import StringIO

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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_report_exporter.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/report_exporter.py tests/test_report_exporter.py
git commit -m "feat: report exporter — CSV, JSON, and comparison matrix"
```

---

## Task 9: FastAPI Backend

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: Create backend/main.py**

```python
# backend/main.py
import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import google.genai as genai
from google.genai import types as gtypes

from backend.config import load_config
from backend.cost_calculator import calculate_turn_cost
from backend.gemini_wrapper import GeminiWrapper, GeminiSession
from backend.mcp_loader import MCPLoader
from backend.metrics_store import MetricsStore, TurnRecord
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
async def export_csv(tmp_path: str = "/tmp/cc_bench_export.csv"):
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
    await websocket.send_json({"type": "session_started", "session_id": session_id})

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
                    input=gtypes.BlobPart(data=data, mime_type="audio/pcm;rate=16000"),
                    end_of_turn=False,
                )

    except WebSocketDisconnect:
        pass
    finally:
        session = await store.get_session(session_id)
        elapsed = gemini_session.elapsed_seconds()
        await store.finalize_session(session_id, elapsed, session.total_cost_usd)


# ── Root: serve dashboard ───────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("frontend/index.html")
```

- [ ] **Step 2: Test server starts**

```bash
cd /path/to/token-usage
uvicorn backend.main:app --reload --port 8000
```

Expected: `Application startup complete` in logs.

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: FastAPI backend — REST API, WebSocket live audio, sim runner integration"
```

---

## Task 10: Frontend — Base Shell + Live Tab

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/app.js`
- Create: `frontend/style.css`

- [ ] **Step 1: Create frontend/index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>CC Token Bench</title>
  <link rel="stylesheet" href="/static/style.css" />
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</head>
<body>
  <header>
    <h1>CC Token Benchmark</h1>
    <nav>
      <button class="tab-btn active" data-tab="live">Live</button>
      <button class="tab-btn" data-tab="sim">Sim Runner</button>
      <button class="tab-btn" data-tab="analytics">Analytics</button>
    </nav>
  </header>

  <!-- Live Tab -->
  <section id="tab-live" class="tab active">
    <div class="controls">
      <label><input type="checkbox" id="live-tools"> MCP Tools</label>
      <label><input type="checkbox" id="live-headroom"> Headroom</label>
      <button id="live-start">Start Conversation</button>
      <button id="live-stop" disabled>Stop</button>
    </div>
    <div class="metrics-row">
      <div class="metric-card" id="live-cost-total">$0.0000</div>
      <div class="metric-card" id="live-tokens-in">0 in</div>
      <div class="metric-card" id="live-tokens-out">0 out</div>
      <div class="metric-card" id="live-duration">0s</div>
    </div>
    <canvas id="live-chart" height="80"></canvas>
    <div id="live-feed"></div>
  </section>

  <!-- Sim Tab -->
  <section id="tab-sim" class="tab">
    <div class="controls">
      <select id="sim-scenario">
        <option value="scenarios/typical_workday.yaml">typical_workday</option>
      </select>
      <label><input type="checkbox" id="sim-tools"> MCP Tools</label>
      <label><input type="checkbox" id="sim-headroom"> Headroom</label>
      <button id="sim-run">Run Scenario</button>
    </div>
    <div id="sim-progress"></div>
    <div id="sim-results"></div>
  </section>

  <!-- Analytics Tab -->
  <section id="tab-analytics" class="tab">
    <div class="controls">
      <input type="number" id="robot-count" value="1" min="1" style="width:60px"> robots
      <button onclick="loadAnalytics()">Refresh</button>
      <a href="/api/export/csv" download>Export CSV</a>
    </div>
    <div id="comparison-table"></div>
    <div class="charts-row">
      <canvas id="cost-bar-chart" height="120"></canvas>
      <canvas id="savings-chart" height="120"></canvas>
    </div>
    <div id="projections"></div>
  </section>

  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create frontend/style.css**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body { font-family: system-ui, sans-serif; background: #0f0f11; color: #e0e0e0; }

header { display: flex; align-items: center; justify-content: space-between; padding: 16px 24px; border-bottom: 1px solid #2a2a2e; }
header h1 { font-size: 1.1rem; font-weight: 600; color: #fff; }

nav { display: flex; gap: 8px; }
.tab-btn { background: #1e1e24; border: 1px solid #333; color: #aaa; padding: 6px 16px; border-radius: 6px; cursor: pointer; }
.tab-btn.active { background: #3b82f6; border-color: #3b82f6; color: #fff; }

.tab { display: none; padding: 24px; }
.tab.active { display: block; }

.controls { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.controls label { display: flex; align-items: center; gap: 6px; cursor: pointer; }
button { background: #3b82f6; color: #fff; border: none; padding: 8px 18px; border-radius: 6px; cursor: pointer; }
button:disabled { background: #334; cursor: default; }
button:hover:not(:disabled) { background: #2563eb; }

.metrics-row { display: flex; gap: 16px; margin-bottom: 20px; }
.metric-card { background: #1a1a22; border: 1px solid #2a2a2e; border-radius: 8px; padding: 16px 20px; font-size: 1.4rem; font-weight: 700; color: #60a5fa; min-width: 120px; text-align: center; }

#live-feed { margin-top: 16px; font-size: 0.85rem; max-height: 300px; overflow-y: auto; }
.feed-row { padding: 6px 0; border-bottom: 1px solid #1e1e24; display: flex; gap: 16px; }
.feed-row .cost { color: #f59e0b; }

#sim-progress { margin-bottom: 16px; }
progress { width: 100%; height: 8px; border-radius: 4px; }

table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #2a2a2e; }
th { background: #1a1a22; color: #aaa; font-weight: 500; }
tr:hover td { background: #1a1a22; }
.savings-positive { color: #34d399; font-weight: 600; }

.charts-row { display: flex; gap: 24px; margin-top: 24px; }
.charts-row canvas { flex: 1; background: #1a1a22; border-radius: 8px; padding: 16px; }

#projections { margin-top: 24px; background: #1a1a22; border-radius: 8px; padding: 20px; }
#projections h3 { margin-bottom: 12px; color: #60a5fa; }
.proj-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.proj-card { background: #0f0f11; border-radius: 6px; padding: 12px; text-align: center; }
.proj-card .label { font-size: 0.75rem; color: #888; }
.proj-card .value { font-size: 1.2rem; font-weight: 700; color: #f0f0f0; margin-top: 4px; }
```

- [ ] **Step 3: Create frontend/app.js**

```javascript
// ── Tab routing ──────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    if (btn.dataset.tab === 'analytics') loadAnalytics();
  });
});

// ── Live Mode ────────────────────────────────────────────────────────────────
let liveWs = null;
let audioContext = null;
let mediaStream = null;
let processor = null;
let liveStartTime = null;
let liveTotalCost = 0;
let liveTotalIn = 0;
let liveTotalOut = 0;
let durationTimer = null;

const liveChart = new Chart(document.getElementById('live-chart'), {
  type: 'line',
  data: { labels: [], datasets: [{ label: 'Cost/turn ($)', data: [], borderColor: '#3b82f6', tension: 0.3, fill: false }] },
  options: { plugins: { legend: { display: false } }, scales: { y: { ticks: { color: '#888' } }, x: { ticks: { color: '#888' } } } }
});

document.getElementById('live-start').addEventListener('click', startLive);
document.getElementById('live-stop').addEventListener('click', stopLive);

async function startLive() {
  liveTotalCost = 0; liveTotalIn = 0; liveTotalOut = 0;
  liveStartTime = Date.now();

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  liveWs = new WebSocket(`${proto}://${location.host}/ws/live`);
  liveWs.binaryType = 'arraybuffer';

  liveWs.onopen = () => {
    liveWs.send(JSON.stringify({
      tools_enabled: document.getElementById('live-tools').checked,
      headroom_enabled: document.getElementById('live-headroom').checked,
    }));
    document.getElementById('live-start').disabled = true;
    document.getElementById('live-stop').disabled = false;
    durationTimer = setInterval(() => {
      const elapsed = Math.round((Date.now() - liveStartTime) / 1000);
      document.getElementById('live-duration').textContent = `${elapsed}s`;
    }, 1000);
  };

  liveWs.onmessage = async (evt) => {
    if (typeof evt.data === 'string') {
      const msg = JSON.parse(evt.data);
      if (msg.type === 'metrics') {
        liveTotalCost += msg.cost_usd;
        liveTotalIn += msg.input_tokens;
        liveTotalOut += msg.output_tokens;
        document.getElementById('live-cost-total').textContent = `$${liveTotalCost.toFixed(4)}`;
        document.getElementById('live-tokens-in').textContent = `${liveTotalIn} in`;
        document.getElementById('live-tokens-out').textContent = `${liveTotalOut} out`;
        addFeedRow(msg.input_tokens, msg.output_tokens, msg.cost_usd);
        liveChart.data.labels.push(liveChart.data.labels.length + 1);
        liveChart.data.datasets[0].data.push(msg.cost_usd);
        liveChart.update();
      }
    } else {
      // PCM audio from Gemini — play it
      await playPcm(evt.data);
    }
  };

  // Mic capture → PCM16 at 16kHz
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000, channelCount: 1 } });
  audioContext = new AudioContext({ sampleRate: 16000 });
  const source = audioContext.createMediaStreamSource(mediaStream);
  processor = audioContext.createScriptProcessor(4096, 1, 1);
  processor.onaudioprocess = (e) => {
    if (!liveWs || liveWs.readyState !== WebSocket.OPEN) return;
    const float32 = e.inputBuffer.getChannelData(0);
    const pcm16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      pcm16[i] = Math.max(-32768, Math.min(32767, float32[i] * 32768));
    }
    liveWs.send(pcm16.buffer);
  };
  source.connect(processor);
  processor.connect(audioContext.destination);
}

async function playPcm(buffer) {
  if (!audioContext) return;
  const int16 = new Int16Array(buffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;
  const audioBuffer = audioContext.createBuffer(1, float32.length, 24000);
  audioBuffer.getChannelData(0).set(float32);
  const src = audioContext.createBufferSource();
  src.buffer = audioBuffer;
  src.connect(audioContext.destination);
  src.start();
}

function addFeedRow(inTok, outTok, cost) {
  const feed = document.getElementById('live-feed');
  const row = document.createElement('div');
  row.className = 'feed-row';
  row.innerHTML = `<span>${inTok} in / ${outTok} out</span><span class="cost">$${cost.toFixed(5)}</span>`;
  feed.prepend(row);
}

function stopLive() {
  if (liveWs) { liveWs.close(); liveWs = null; }
  if (processor) { processor.disconnect(); processor = null; }
  if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
  if (audioContext) { audioContext.close(); audioContext = null; }
  clearInterval(durationTimer);
  document.getElementById('live-start').disabled = false;
  document.getElementById('live-stop').disabled = true;
}

// ── Sim Runner ───────────────────────────────────────────────────────────────
document.getElementById('sim-run').addEventListener('click', async () => {
  const body = {
    scenario_path: document.getElementById('sim-scenario').value,
    tools_enabled: document.getElementById('sim-tools').checked,
    headroom_enabled: document.getElementById('sim-headroom').checked,
  };

  const { run_id } = await fetch('/api/sim/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());
  const progressDiv = document.getElementById('sim-progress');
  progressDiv.innerHTML = `<p>Running... <progress id="prog" value="0" max="100"></progress></p>`;

  const poll = setInterval(async () => {
    const status = await fetch(`/api/sim/status/${run_id}`).then(r => r.json());
    if (status.total > 0) {
      document.getElementById('prog').value = (status.progress / status.total) * 100;
    }
    if (status.status === 'done') {
      clearInterval(poll);
      progressDiv.innerHTML = `<p style="color:#34d399">Done! Session: ${status.session_id}</p>`;
      loadAnalytics();
    }
  }, 500);
});

// ── Analytics ────────────────────────────────────────────────────────────────
let costBarChart = null;

async function loadAnalytics() {
  const matrix = await fetch('/api/comparison').then(r => r.json());
  const robots = parseInt(document.getElementById('robot-count').value) || 1;

  // Table
  const tableHtml = `<table>
    <thead><tr>
      <th>Scenario</th><th>Tools</th><th>Headroom</th>
      <th>Duration</th><th>Total Cost</th><th>Cost/hr</th>
      <th>Daily (8hr)</th><th>Monthly</th>
    </tr></thead>
    <tbody>${matrix.map(row => {
      const costPerHr = row.cost_per_hour_usd * robots;
      const daily = costPerHr * 8;
      const monthly = daily * 22;
      return `<tr>
        <td>${row.scenario_name}</td>
        <td>${row.tools_enabled ? '✓' : '—'}</td>
        <td>${row.headroom_enabled ? '✓' : '—'}</td>
        <td>${Math.round(row.duration_seconds / 60)}min</td>
        <td>$${(row.total_cost_usd * robots).toFixed(4)}</td>
        <td>$${costPerHr.toFixed(4)}</td>
        <td>$${daily.toFixed(3)}</td>
        <td>$${monthly.toFixed(2)}</td>
      </tr>`;
    }).join('')}</tbody>
  </table>`;
  document.getElementById('comparison-table').innerHTML = tableHtml;

  // Bar chart
  if (costBarChart) costBarChart.destroy();
  costBarChart = new Chart(document.getElementById('cost-bar-chart'), {
    type: 'bar',
    data: {
      labels: matrix.map(r => `${r.scenario_name}\n${r.tools_enabled?'+tools':''}${r.headroom_enabled?'+headroom':''}`),
      datasets: [{ label: 'Total Cost ($)', data: matrix.map(r => r.total_cost_usd * robots), backgroundColor: '#3b82f6' }]
    },
    options: { plugins: { legend: { display: false } }, scales: { y: { ticks: { color: '#888' } }, x: { ticks: { color: '#888' } } } }
  });

  // Projections
  if (matrix.length > 0) {
    const baseline = matrix[0];
    const costPerHr = baseline.cost_per_hour_usd * robots;
    document.getElementById('projections').innerHTML = `
      <h3>Cost Projections (${robots} robot${robots > 1 ? 's' : ''}) — baseline config</h3>
      <div class="proj-grid">
        <div class="proj-card"><div class="label">Per Hour</div><div class="value">$${costPerHr.toFixed(3)}</div></div>
        <div class="proj-card"><div class="label">Per Day (8hr)</div><div class="value">$${(costPerHr * 8).toFixed(2)}</div></div>
        <div class="proj-card"><div class="label">Per Month (22d)</div><div class="value">$${(costPerHr * 8 * 22).toFixed(2)}</div></div>
        <div class="proj-card"><div class="label">Per Year</div><div class="value">$${(costPerHr * 8 * 260).toFixed(0)}</div></div>
      </div>`;
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: browser dashboard — live audio tab, sim runner tab, analytics tab"
```

---

## Task 11: Integration Test — Full Run

- [ ] **Step 1: Run all unit tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Start server**

```bash
uvicorn backend.main:app --reload --port 8000
```

Expected: `Application startup complete`

- [ ] **Step 3: Run a sim scenario via API**

```bash
curl -X POST http://localhost:8000/api/sim/run \
  -H 'Content-Type: application/json' \
  -d '{"scenario_path": "scenarios/typical_workday.yaml", "tools_enabled": false, "headroom_enabled": false}'
```

Expected: `{"run_id": "<uuid>"}`

Poll until done:
```bash
curl http://localhost:8000/api/sim/status/<run_id>
```

Expected: `{"status": "done", "session_id": "<uuid>", ...}`

- [ ] **Step 4: Check comparison matrix**

```bash
curl http://localhost:8000/api/comparison | python -m json.tool
```

Expected: JSON array with at least 1 session, fields include `total_cost_usd`, `cost_per_hour_usd`.

- [ ] **Step 5: Open dashboard in browser**

Navigate to `http://localhost:8000`. Verify:
- All 3 tabs render without JS errors
- Analytics tab shows the sim session in the table
- Export CSV link downloads a file

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: complete CC token benchmarking tool"
```

---

## Verification

1. `pytest tests/ -v` → all tests green
2. Sim run via API → session appears in `/api/comparison`
3. Live tab → mic → hear Gemini respond → token metrics update in real-time
4. Analytics tab → cost projections accurate against pricing table screenshot
5. Export CSV → opens in Excel/Sheets with correct columns
