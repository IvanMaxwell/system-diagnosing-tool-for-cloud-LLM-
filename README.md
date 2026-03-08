# System Diagnostics API for LLMs
### ~78% token reduction on standard diagnostic queries

A lightweight local FastAPI service that exposes real-time Windows system diagnostics to cloud LLMs (Claude, GPT, Gemini, Ollama). Instead of dumping raw metrics into context, it runs a **delta-capture polling engine** and compresses all output through a **Structured Symptom Compression (SSC)** pipeline — so the LLM receives a 60-100 token narrative instead of a 400-600 token raw data dump.

---

## Architecture

```
Windows System
    │
    ▼
[Polling Engine] ←── every 5s, delta-only writes
    │
    ▼
[snapshot.json] ←── 500KB capped state file
    │
    ▼
[Intent Classifier] ←── keyword-based category routing
    │
    ▼
[Relevant Fetcher] ←── pulls only what the intent needs
    │
    ▼
[SSC Compressor] ←── anomaly check → causal ID → narrative
    │
    ▼
[Cloud LLM] ←── receives typed JSON, ~60-100 tokens
```

---

## Token Reduction Benchmark

| Query | Raw dump tokens | SSC output tokens | Reduction |
|---|---|---|---|
| "why is my system slow" | 487 | 94 | **81%** |
| "what processes are running" | 612 | 118 | **81%** |
| "check memory" | 203 | 52 | **74%** |
| "get hardware specs" | 341 | 87 | **74%** |

---

## Quickstart

```bash
git clone <repo>
cd tool1-system-diagnostics
pip install -r requirements.txt
# Edit config.yaml — set your api_key
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API docs at: `http://localhost:8000/docs`

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Uptime, polling status, config |
| GET | `/snapshot` | Raw current state (debug) |
| POST | `/query` | Main endpoint — intent in, SSC out |
| GET | `/memory/recent` | Last 10 diagnostic events |
| POST | `/query/dynamic` | DQE: submit code + explanation |
| POST | `/query/dynamic/execute` | DQE: execute approved code |

---

## Authentication

All requests require header: `x-api-key: <your-key>`

Set your key in `config.yaml`:
```yaml
api_key: "your-secret-key"
```

---

## LLM Integration

### Claude (tool_use)
```python
import anthropic, json

client = anthropic.Anthropic()
tool_def = json.load(open("adapters/claude.json"))

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=[{"name": tool_def["name"], "description": tool_def["description"], "input_schema": tool_def["input_schema"]}],
    messages=[{"role": "user", "content": "Why is my PC slow right now?"}]
)
# When tool_use block appears, call:
# POST http://localhost:8000/query
# {"intent": <tool_input.intent>, "model": "claude"}
# x-api-key: <your-key>
```

### OpenAI (function calling)
```python
import openai, json, requests

client = openai.OpenAI()
tool_def = json.load(open("adapters/openai.json"))

response = client.chat.completions.create(
    model="gpt-4o",
    tools=[tool_def],
    messages=[{"role": "user", "content": "Check my RAM usage"}]
)
# On tool_calls, dispatch to:
# POST http://localhost:8000/query
# {"intent": args["intent"], "model": "openai"}
# x-api-key: <your-key>
```

### Gemini (function calling)
```python
import google.generativeai as genai, json

genai.configure(api_key="YOUR_GEMINI_KEY")
tool_def = json.load(open("adapters/gemini.json"))
# Pass tool_def to genai.GenerativeModel tools parameter
# On function_call response, POST to /query with intent
```

### Ollama (local, OpenAI-compatible)
```python
# Uses same pattern as OpenAI adapter
# Base URL: http://localhost:11434/v1
# Load adapters/ollama.json as the tool definition
```

### Generic (any OpenAPI-compatible client)
```
Load adapters/generic_openapi.json into your LLM client.
Points to http://localhost:8000 by default.
```

---

## Dynamic Query Expansion (DQE)

For queries outside the 4 built-in categories, DQE lets the LLM write constrained Python to fetch custom system data.

**Enable in config.yaml:**
```yaml
dqe:
  enabled: true
```

**Flow:**
1. LLM queries `/query` → receives `dqe_required` + prompt
2. LLM writes code + plain English explanation
3. LLM POSTs to `/query/dynamic`
4. **Safety filter runs** (AST-based: no network, no file writes, whitelist imports only)
5. User sees explanation + code:

```
┌─────────────────────────────────────────────────────┐
│  The LLM needs additional system data               │
│                                                     │
│  WHAT IT WILL DO:                                   │
│  Read all installed Windows services and their      │
│  current running status.                            │
│                                                     │
│  CODE:                                              │
│  import subprocess                                  │
│  r = subprocess.run(['sc','query'], ...)            │
│  print(r.stdout)                                    │
│                                                     │
│  POST approval_token to /query/dynamic/execute      │
└─────────────────────────────────────────────────────┘
```

6. User approves → code executes in subprocess sandbox (5s timeout)
7. Result SSC-compressed → returned to LLM

---

## Intent Categories

| Category | Trigger Keywords | Data Returned |
|---|---|---|
| performance | slow, lag, cpu, freeze, speed | CPU + top processes |
| process | process, running, spawned, task | Full process list + new PIDs |
| resource | memory, ram, disk, network, storage | RAM + disk I/O + network |
| hardware | os, specs, hardware, version, machine | OS info + static CPU/RAM specs |
| no_match | anything else | DQE path (if enabled) |

---

## Causal Memory

Every query is written to SQLite. The service tracks how many times each category was queried and includes `prior_occurrences` in every SSC response — giving the LLM historical pattern awareness without any extra tokens.
