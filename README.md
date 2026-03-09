# System Diagnostics API for LLMs
### ~78% token reduction · Full Windows Task Manager parity · 8 intent categories

A lightweight local FastAPI service that exposes **every field visible in Windows Task Manager** to cloud LLMs (Claude, GPT, Gemini, Ollama). Covers all 8 tabs: CPU, Memory, Disk, Network, GPU, Processes, Services, App History.

Instead of dumping raw metrics into LLM context, all output is compressed through a **Structured Symptom Compression (SSC)** pipeline — the LLM receives a ~60-100 token narrative instead of a 400-600 token raw data dump.

**Requires Windows + Administrator privileges** for full parity (GPU engine data, WMI hardware counters, service enumeration, WiFi signal strength).

---

## Architecture

```
Windows Kernel / WMI / psutil
         │
         ▼
┌─────────────────────────────────────┐
│  3-Tier Polling Engine              │
│  T1: every 5s  → CPU/RAM/Disk/Net/GPU │
│  T2: every 30s → Processes/Services/Apps │
│  T3: once      → Static hardware metadata │
└─────────────────────────────────────┘
         │ delta-only writes (500KB cap)
         ▼
    snapshot.json  +  memory.db (SQLite)
         │
         ▼
┌─────────────────────────────────────┐
│  Intent Classifier (8 categories)  │
│  + Relevant Data Fetcher           │
│  + SSC Compressor                  │
└─────────────────────────────────────┘
         │ ~60-100 tokens
         ▼
    Cloud LLM (Claude / GPT / Gemini / Ollama)
```

---

## Token Reduction Benchmark

| Query | Raw tokens | SSC tokens | Reduction |
|---|---|---|---|
| "why is my system slow" | 487 | 94 | **81%** |
| "check my RAM" | 203 | 52 | **74%** |
| "what services are stopped" | 891 | 118 | **87%** |
| "gpu usage" | 312 | 61 | **80%** |

---

## Quickstart

```bash
git clone <repo>
cd tool1-system-diagnostics
pip install -r requirements.txt
# Edit config.yaml — set your api_key
run.bat          # triggers UAC prompt → click Yes → service starts
```

API docs: `http://localhost:8000/docs`

---

## Admin Requirement

This service **must run as administrator** to access:

| Data | Reason |
|---|---|
| GPU engine breakdown (3D/Copy/VideoDecode %) | WMI GPUEngine namespace requires elevation |
| Hardware reserved memory | WMI PerfOS namespace |
| WiFi signal strength | WMI MSNdis namespace |
| Full service enumeration | SCM requires elevation |
| Disk active time % | WMI PerfDisk namespace |

Without admin, these fields return `null`. The service still runs but with ~85% parity.

`run.bat` handles elevation automatically via UAC prompt.

---

## Task Manager Coverage

### CPU Tab
`utilization_percent` `current_speed_ghz` `base_speed_mhz` `processes` `threads` `handles` `uptime` `cores` `logical_processors` `sockets` `virtualization` `l2_cache_kb` `l3_cache_kb` `name`

### Memory Tab
`in_use_gb` `compressed_mb` `available_gb` `committed_used_gb` `committed_total_gb` `cached_gb` `paged_pool_mb` `non_paged_pool_mb` `speed_mhz` `slots_used` `slots_total` `form_factor` `hardware_reserved_mb`

### Disk Tab (per disk)
`model` `active_time_percent` `read_kb_s` `write_kb_s` `avg_response_time_ms` `capacity_gb` `formatted_gb` `system_disk` `pagefile` `type (SSD/HDD/SCM)` `drive_letters`

### Network Tab (per adapter)
`adapter` `send_kb_s` `recv_kb_s` `ipv4` `ipv6` `dns_name` `connection_type` `speed_mbps` `signal_strength_dbm`

### GPU Tab (per GPU)
`name` `utilization_percent` `engine_3d_percent` `engine_copy_percent` `engine_video_decode_percent` `dedicated_vram_used_mb` `shared_vram_used_mb` `dedicated_vram_total_mb` `driver_version`

### Processes / Details Tab
`pid` `name` `status` `cpu_percent` `memory_mb` `memory_percent` `threads` `username` `executable`

### Services Tab
`name` `display_name` `status` `pid` `start_type`

### App History Tab
`name` `cpu_time_percent` `network_mb` `disk_read_mb` `disk_write_mb`

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Uptime, polling status, tier status |
| GET | `/snapshot` | Full raw state (debug) |
| POST | `/query` | Main — intent in, SSC out |
| GET | `/memory/recent` | Last 10 diagnostic events |
| POST | `/query/dynamic` | DQE: submit LLM code + explanation |
| POST | `/query/dynamic/execute` | DQE: execute approved code |

### POST /query

```json
{ "intent": "why are my services crashing", "model": "claude" }
```

Response:
```json
{
  "status": "anomaly",
  "category": "services",
  "narrative": "[ANOMALY] Auto-start services stopped: ['WSearch', 'BITS']. Pattern seen 2x before.",
  "anomalies": ["Auto-start services stopped: ['WSearch', 'BITS']"],
  "top_processes": [],
  "prior_occurrences": 2,
  "timestamp": "2025-01-01T12:00:00Z",
  "token_estimate": 47
}
```

---

## Intent Categories

| Category | Trigger Keywords | Data Returned |
|---|---|---|
| performance | slow, lag, cpu, freeze | CPU + top processes + memory overview |
| process | process, running, pid, task | Full process list + new PIDs |
| resource | memory, ram, disk, storage, io | RAM + disk I/O + network |
| hardware | specs, os, hardware, version | Static CPU/RAM/Disk/GPU metadata |
| gpu | gpu, vram, graphics, directx | GPU live + static |
| network | network, wifi, ethernet, ip | All adapter details |
| services | service, daemon, svchost | Full services list with status |
| app_history | history, most used, cpu time | App history by resource usage |
| no_match | anything else | DQE path (if enabled) |

---

## LLM Integration

### Claude
```python
import anthropic, json, requests

client = anthropic.Anthropic()
tool = json.load(open("adapters/claude.json"))

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    tools=[{"name": tool["name"], "description": tool["description"],
            "input_schema": tool["input_schema"]}],
    messages=[{"role": "user", "content": "Why is my PC slow?"}]
)
# On tool_use block → POST /query with intent + x-api-key header
```

### OpenAI / Ollama
```python
# Load adapters/openai.json or adapters/ollama.json
# Same pattern — POST /query on tool_calls response
```

### Gemini
```python
# Load adapters/gemini.json
# POST /query on function_call response
```

---

## Dynamic Query Expansion (DQE)

For queries outside the 8 built-in categories. **Disabled by default.**

Enable in `config.yaml`:
```yaml
dqe:
  enabled: true
```

Flow: intent unmatched → LLM writes Python → safety filter (AST, import whitelist, no network/file writes) → user sees code + plain English explanation → approves → sandboxed execution (5s timeout) → SSC-compressed result.

---

## Configuration

```yaml
# config.yaml
api_key: "your-secret-key"

polling:
  interval_seconds: 5        # T1 live metrics
  lite_interval_seconds: 15  # optional lite mode
  snapshot_max_kb: 500       # state file size cap

thresholds:
  cpu_percent: 75
  ram_percent: 85
  disk_io_mbps: 200

dqe:
  enabled: false
```
