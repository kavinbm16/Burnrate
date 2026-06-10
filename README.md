# Burnrate

**Gemini Live cost lab for voice AI robots.**

Burnrate measures real token economics for speech-to-speech agents — live mic sessions, fast-forward scenario sims, and side-by-side cost analytics. Built to answer one question with data: *what does one robot cost per hour, day, and month?*

Developed for Machani Robotics **CC**, a desktop robot powered by Gemini Live. Works for any Gemini Live + MCP + headroom setup.

---

## Why Burnrate?

Pricing a voice robot from API list rates alone is misleading. Actual cost depends on:

- **Audio I/O** — dominant; billed by the minute, not tokens
- **System prompt** — fixed per session
- **MCP tool definitions** — scales with connected servers
- **Conversation context** — grows over time; compressible with [headroom](https://github.com/humanlayer/headroom)

Burnrate runs the same conversation under four configurations and extrapolates to fleet-scale numbers — session → daily → monthly → *N* robots.

```
┌──────────────────────────────────────────────────────────────────┐
│  ◉ BURNRATE                                                      │
│                                                                  │
│   Live          Sim              Analytics                       │
│   mic → API     YAML replay      compare · project · export      │
│   real-time     8hr in ~3min     CSV for finance                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## Features

| Mode | What it does |
|------|----------------|
| **Live** | Browser mic → PCM → Gemini Live → speaker. Per-turn token feed and running cost. |
| **Sim** | Replay YAML scenario scripts at full API speed. Extrapolate audio cost from turn duration. |
| **Analytics** | Comparison matrix across tools/headroom configs. Daily, monthly, and fleet projections. |

**Benchmark matrix** — four configs × multiple durations:

| Config | MCP Tools | Headroom |
|--------|-----------|----------|
| Baseline | off | off |
| Tools only | on | off |
| Headroom only | off | on |
| Full stack | on | on |

---

## Architecture

```mermaid
flowchart TB
    subgraph Browser["Browser Dashboard"]
        Live["Live Tab"]
        Sim["Sim Tab"]
        Analytics["Analytics Tab"]
    end

    subgraph Backend["FastAPI Backend"]
        GW["GeminiWrapper"]
        MCP["MCPLoader"]
        SR["SimRunner"]
        MS["MetricsStore · SQLite"]
        RE["ReportExporter"]
    end

    subgraph External["External Services"]
        Gemini["Gemini Live API"]
        Servers["MCP Servers"]
        HR["Headroom · optional"]
    end

    Live -->|"WebSocket /ws/live"| GW
    Sim -->|"REST /api/sim/run"| SR
    Analytics -->|"REST /api/comparison"| RE

    GW --> Gemini
    GW --> HR
    MCP --> Servers
    SR --> GW
    GW --> MS
    SR --> MS
    RE --> MS
```

Every session is stored as **sessions + turns** in SQLite. Each turn captures `usageMetadata` from Gemini and maps it into four cost buckets.

---

## Cost buckets

| Bucket | Pricing | Notes |
|--------|---------|-------|
| Audio input | $0.005 / min | Dominant at scale |
| Audio output | $0.018 / min | Dominant at scale |
| Text input | $0.75 / 1M tokens | System prompt, tools, context |
| Text output | $4.50 / 1M tokens | Responses, tool calls |

Rates are configurable in `mcp.toml` — update when Gemini pricing changes.

---

## Quick start

### Prerequisites

- Python 3.11+
- A Gemini API key with Live API access
- *(Optional)* MCP servers and `headroom` for full benchmark matrix

### Install

```bash
git clone <repo-url> burnrate
cd burnrate
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

Edit `mcp.toml`:

```toml
[gemini]
api_key = "YOUR_GEMINI_API_KEY"
model   = "gemini-3.1-flash-live-preview"

[pricing]
audio_input_per_min   = 0.005
audio_output_per_min  = 0.018
text_input_per_mtok   = 0.75
text_output_per_mtok  = 4.50

# [mcp_servers.filesystem]
# type    = "stdio"
# command = "npx"
# args    = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

### Run

```bash
uvicorn backend.main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) for the dashboard.

### First sim run (API)

```bash
curl -X POST http://localhost:8000/api/sim/run \
  -H 'Content-Type: application/json' \
  -d '{
    "scenario_path": "scenarios/typical_workday.yaml",
    "tools_enabled": false,
    "headroom_enabled": false
  }'
```

Poll until complete:

```bash
curl http://localhost:8000/api/sim/status/<run_id>
```

View results:

```bash
curl http://localhost:8000/api/comparison | python -m json.tool
```

---

## Scenario format

Scenarios live in `scenarios/*.yaml`. Sim mode replays turns against Gemini and extrapolates audio cost from `avg_turn_duration_sec`.

```yaml
name: typical_workday
description: "Simulates a typical 30-minute robot interaction"
avg_turn_duration_sec: 25
system_prompt: "You are CC, a helpful desktop robot assistant."
turns:
  - "Good morning! What's the weather like today?"
  - "Set a reminder for my 3pm meeting."
  # ...
repeat: 16   # multiply turns to target duration (e.g. 8-hour workday)
```

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard UI |
| `GET` | `/api/sessions` | List all benchmark sessions |
| `GET` | `/api/sessions/{id}/turns` | Turn-level token breakdown |
| `GET` | `/api/comparison` | Comparison matrix for analytics |
| `POST` | `/api/sim/run` | Start a scenario sim (`scenario_path`, `tools_enabled`, `headroom_enabled`) |
| `GET` | `/api/sim/status/{run_id}` | Sim progress and result |
| `GET` | `/api/export/csv` | Download sessions as CSV |
| `GET` | `/api/export/json` | Full session + turn JSON |
| `WS` | `/ws/live` | Live audio session (send init JSON, then PCM16 chunks) |

**Live WebSocket init message:**

```json
{ "tools_enabled": false, "headroom_enabled": false }
```

Server sends `session_started`, streaming `metrics` events, and PCM audio bytes.

---

## Project layout

```
burnrate/
├── mcp.toml                  # API keys, pricing, MCP server configs
├── scenarios/
│   └── typical_workday.yaml  # Example benchmark script
├── backend/
│   ├── main.py               # FastAPI app — REST, WebSocket, static UI
│   ├── config.py             # TOML loader
│   ├── gemini_wrapper.py     # Gemini Live SDK + usageMetadata capture
│   ├── mcp_loader.py           # MCP stdio/http → Gemini tool definitions
│   ├── sim_runner.py         # YAML scenario replay engine
│   ├── cost_calculator.py    # Per-turn and extrapolated pricing
│   ├── metrics_store.py      # SQLite sessions + turns
│   └── report_exporter.py    # CSV, JSON, comparison matrix
├── frontend/                 # Dashboard (Live · Sim · Analytics tabs)
└── tests/
```

---

## Exports

**CSV** — one row per session; columns include `tools_enabled`, `headroom_enabled`, `duration_seconds`, `total_cost_usd`. Drop into a pricing spreadsheet.

**JSON** — full session records with per-turn token breakdowns for archival or downstream tooling.

---

## Development

```bash
pytest tests/ -v
```

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| AI | `google-genai` — Gemini Live API |
| Context | `headroom` — optional message compression |
| Tools | `mcp` — Model Context Protocol servers |
| Storage | SQLite via `aiosqlite` |
| Frontend | Vanilla HTML/JS + Chart.js |

---

## License

Internal — Machani Robotics. Contact the team before external distribution.
