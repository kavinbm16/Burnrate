# CC Token Benchmarking Tool — Design Spec
**Date:** 2026-06-10  
**Project:** Machani Robotics — CC Desktop Robot  
**Model:** `gemini-3.1-flash-live-preview`

---

## Context

CC is a desktop robot using Gemini 3.1 Flash Live for real-time speech-to-speech. To fix monthly pricing per unit, we need accurate token usage data across realistic usage scenarios. This tool benchmarks token consumption and cost across all variable axes: MCP tools on/off, headroom compression on/off, and session durations up to 8 hours.

---

## Goals

1. Measure real token costs for CC's audio conversations
2. Quantify MCP tool overhead (token cost of tool definitions + calls)
3. Quantify headroom savings on conversation context
4. Produce a cost matrix: per-session, per-day, per-month, per-N-robots
5. Be usable by non-engineers (shareable browser dashboard)

---

## Pricing Reference

| Type | Rate |
|------|------|
| Audio input | $0.005 / min |
| Audio output | $0.018 / min |
| Text input (system, tools, context) | $0.75 / 1M tokens |
| Text output (tool calls, responses) | $4.50 / 1M tokens |

Configurable in `mcp.toml` — update when rates change.

---

## Architecture

```
Browser UI
  ├── Live Mode tab   (mic → audio → Gemini → speaker)
  ├── Sim Runner tab  (run scenario scripts, watch token burn)
  └── Analytics tab   (compare sessions, cost projections)
        │  WebSocket (live) / REST (sim + analytics)
        ▼
FastAPI Backend
  ├── GeminiLiveWrapper    ← wraps SDK, captures usageMetadata per turn
  │     ├── optional: headroom.compress(messages) before send
  │     └── optional: inject MCP tool definitions
  ├── MCPLoader            ← reads mcp.toml, connects servers, pulls tool schemas
  ├── SimRunner            ← replays YAML scenario scripts, fast-forward mode
  ├── MetricsStore         ← SQLite: sessions / turns / token breakdown / cost
  └── ReportExporter       ← CSV + JSON export
        │
        ▼
Gemini Live API  +  MCP Servers (from mcp.toml)  +  Headroom (optional)
```

---

## Configuration — `mcp.toml`

```toml
[gemini]
api_key = "..."
model   = "gemini-3.1-flash-live-preview"

[pricing]
audio_input_per_min   = 0.005
audio_output_per_min  = 0.018
text_input_per_mtok   = 0.75
text_output_per_mtok  = 4.50

[mcp_servers.example_tool]
type    = "http"
url     = "http://localhost:3001"

[mcp_servers.another_tool]
type    = "stdio"
command = "npx"
args    = ["-y", "@modelcontextprotocol/server-filesystem"]
```

---

## Token Cost Buckets

Every session is broken into 4 measured buckets:

| Bucket | Pricing type | Notes |
|--------|-------------|-------|
| Audio I/O | time-based | dominant cost; input + output separate |
| System prompt | text tokens | fixed per session |
| Tool definitions | text tokens | scales with # MCP tools loaded |
| Conversation context | text tokens | grows over time; headroom targets this |

Headroom compression affects **bucket 4 only**. The dashboard highlights this delta.

---

## Two Modes

### Live Mode
- Browser microphone → PCM audio chunks → WebSocket → backend
- Backend streams to Gemini Live SDK
- Audio response streams back → browser plays it
- `usageMetadata` captured on every server turn
- Dashboard updates in real-time: cost/min, running total per bucket

### Sim Mode
- YAML scenario files define conversation as text turns
- `SimRunner` sends turns to Gemini text API at full speed (no audio latency)
- Real token counts returned; audio cost extrapolated via `turns × avg_duration × rate`
- 8-hour simulation runs in ~2-3 minutes
- Multiple runs queued to fill comparison matrix

**Scenario file format:**
```yaml
name: typical_workday
avg_turn_duration_sec: 30
turns:
  - "Good morning, what's on my schedule today?"
  - "Set a reminder for the 3pm meeting"
  - "Search for the latest quarterly report"
  # ... more turns
repeat: 16   # × turns to simulate target duration
```

---

## Benchmark Matrix

4 configurations × multiple durations:

| Config | Tools | Headroom |
|--------|-------|----------|
| Baseline | OFF | OFF |
| Tools only | ON | OFF |
| Headroom only | OFF | ON |
| Full | ON | ON |

Durations: 15min, 1hr, 4hr, 8hr (sim); real-time (live).

---

## Dashboard — 3 Tabs

### Live Tab
- Real-time cost/min gauge + running session total
- Donut chart: cost split by bucket (audio / system / tools / context)
- Turn feed: each turn → tokens in / tokens out / incremental cost

### Sim Tab
- Scenario selector, Tools toggle, Headroom toggle
- Run button → live progress bar → results
- Queue multiple configs to build matrix in one go

### Analytics Tab
- Side-by-side comparison table across all completed runs
- Cost extrapolation card: session → daily → monthly → per-N-robots
- Key insight cards:
  - "Headroom reduces context cost by X%"
  - "MCP tools add $Y/day per robot"
- Export buttons: CSV (for pricing spreadsheet), JSON (for records)

**Comparison matrix (auto-filled):**
```
                   No Headroom    With Headroom    Savings %
No Tools  8hr      $X.XX          $X.XX            XX%
With Tools 8hr     $X.XX          $X.XX            XX%
Tool overhead      $X.XX / day
```

---

## Project Structure

```
token-usage/
├── mcp.toml                  ← config: API keys, pricing, MCP servers
├── scenarios/
│   └── typical_workday.yaml
├── backend/
│   ├── main.py               ← FastAPI app, WebSocket + REST
│   ├── gemini_wrapper.py     ← Gemini Live SDK wrapper, usageMetadata capture
│   ├── mcp_loader.py         ← TOML loader, MCP server connections, tool schemas
│   ├── sim_runner.py         ← scenario replay engine
│   ├── metrics_store.py      ← SQLite schema + queries
│   └── report_exporter.py   ← CSV/JSON export
├── frontend/
│   ├── index.html
│   ├── app.js                ← tab routing, WebSocket client, Chart.js charts
│   └── style.css
└── requirements.txt
```

---

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Backend | Python + FastAPI | Gemini SDK is Python-first; async WebSocket support |
| Gemini | `google-genai` SDK | Official SDK for Live API |
| Context compression | `headroom` library | `compress(messages)` call before send |
| MCP | `mcp` Python SDK | Connect to stdio/http MCP servers |
| Storage | SQLite | Zero-config, portable, enough for bench data |
| Frontend | Vanilla HTML/JS + Chart.js | No build step, fast to iterate |

---

## Verification

1. `python backend/main.py` → server starts, loads `mcp.toml`
2. Open browser → Live tab → speak → confirm audio plays back, tokens appear in feed
3. Sim tab → run "typical_workday" with Tools OFF, Headroom OFF → matrix row populates
4. Repeat with all 4 configs → full matrix visible in Analytics tab
5. Export CSV → verify columns: session_id, config, duration, audio_cost, text_cost, total_cost
6. Check headroom savings % is non-zero when enabled
