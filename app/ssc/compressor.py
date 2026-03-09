"""
compressor.py — Structured Symptom Compression (SSC).
Converts raw system data into minimal-token LLM-ready narratives.
Output schema is fixed. token_estimate always included.
"""
from datetime import datetime, timezone
from typing import Any

from app.ssc.thresholds import cpu_anomaly, ram_anomaly, disk_anomaly, process_spawned

# ── Known game requirements for compatibility checks ──────────────────────────

GAME_REQUIREMENTS: dict[str, dict] = {
    "rdr2": {
        "name": "Red Dead Redemption 2",
        "min_ram_gb": 8,
        "rec_ram_gb": 12,
        "min_vram_mb": 4096,
        "rec_vram_mb": 8192,
        "min_disk_gb": 150,
        "min_cpu_cores": 4,
    },
    "gta5": {
        "name": "GTA V",
        "min_ram_gb": 4,
        "rec_ram_gb": 8,
        "min_vram_mb": 1024,
        "rec_vram_mb": 4096,
        "min_disk_gb": 72,
        "min_cpu_cores": 4,
    },
    "cyberpunk": {
        "name": "Cyberpunk 2077",
        "min_ram_gb": 8,
        "rec_ram_gb": 16,
        "min_vram_mb": 6144,
        "rec_vram_mb": 8192,
        "min_disk_gb": 70,
        "min_cpu_cores": 6,
    },
    "fortnite": {
        "name": "Fortnite",
        "min_ram_gb": 8,
        "rec_ram_gb": 16,
        "min_vram_mb": 2048,
        "rec_vram_mb": 4096,
        "min_disk_gb": 30,
        "min_cpu_cores": 4,
    },
}


def _detect_game(intent: str) -> str | None:
    """Detect a game reference in the intent string."""
    lowered = intent.lower()
    for key in GAME_REQUIREMENTS:
        if key in lowered:
            return key
    return None


def _game_compat_check(intent: str, data: dict[str, Any]) -> str | None:
    """Generate a yes/no/maybe game compatibility summary."""
    game_key = _detect_game(intent)
    if not game_key:
        return None

    req = GAME_REQUIREMENTS[game_key]
    issues: list[str] = []
    okay: list[str] = []

    # RAM
    mem = data.get("memory") or {}
    total_ram_gb = mem.get("committed_total_gb", 0) or 0
    if total_ram_gb > 0:
        if total_ram_gb >= req["rec_ram_gb"]:
            okay.append(f"RAM ✓ ({total_ram_gb:.0f}GB, recommended {req['rec_ram_gb']}GB)")
        elif total_ram_gb >= req["min_ram_gb"]:
            okay.append(f"RAM ⚠ ({total_ram_gb:.0f}GB meets minimum, recommended {req['rec_ram_gb']}GB)")
        else:
            issues.append(f"RAM ✗ ({total_ram_gb:.0f}GB, minimum {req['min_ram_gb']}GB required)")

    # VRAM
    gpu_static = data.get("gpu_static") or []
    gpu_live = data.get("gpu") or []
    vram_mb = 0
    gpu_name = "Unknown GPU"
    if gpu_static:
        g = gpu_static[0]
        gpu_name = g.get("name", "Unknown GPU") or "Unknown GPU"
        vram_mb = g.get("dedicated_vram_total_mb", 0) or 0
    elif gpu_live:
        vram_mb = gpu_live[0].get("dedicated_vram_used_mb", 0) or 0

    if vram_mb > 0:
        if vram_mb >= req["rec_vram_mb"]:
            okay.append(f"VRAM ✓ ({vram_mb:.0f}MB, recommended {req['rec_vram_mb']}MB)")
        elif vram_mb >= req["min_vram_mb"]:
            okay.append(f"VRAM ⚠ ({vram_mb:.0f}MB meets minimum, recommended {req['rec_vram_mb']}MB)")
        else:
            issues.append(f"VRAM ✗ ({vram_mb:.0f}MB, minimum {req['min_vram_mb']}MB required)")

    # Disk free space
    disk_usage = data.get("disk_usage") or []
    max_free = max((d.get("free_gb", 0) for d in disk_usage if "free_gb" in d), default=0)
    if max_free > 0:
        if max_free >= req["min_disk_gb"]:
            okay.append(f"Storage ✓ ({max_free:.0f}GB free, {req['min_disk_gb']}GB needed)")
        else:
            issues.append(f"Storage ✗ ({max_free:.0f}GB free, need {req['min_disk_gb']}GB for {req['name']})")

    # CPU cores
    cpu_static = data.get("cpu_static") or {}
    cores = cpu_static.get("cores", 0) or 0
    if cores > 0:
        if cores >= req["min_cpu_cores"]:
            okay.append(f"CPU ✓ ({cores} cores)")
        else:
            issues.append(f"CPU ✗ ({cores} cores, minimum {req['min_cpu_cores']} required)")

    if not issues and not okay:
        return f"[{req['name']}] Compatibility check: Not enough spec data collected yet."

    verdict = "YES ✓" if not issues else ("MAYBE ⚠" if len(issues) <= 1 else "NO ✗")
    lines = [f"[{req['name']}] Can you run it? {verdict}"]
    if okay:
        lines.extend(f"  {o}" for o in okay)
    if issues:
        lines.extend(f"  {i}" for i in issues)
    return "\n".join(lines)


# ── Token estimation ──────────────────────────────────────────────────────────

def _tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _top_procs(processes: list[dict], n: int = 3) -> list[dict]:
    return sorted(processes, key=lambda p: p.get("cpu_percent", 0), reverse=True)[:n]


# ── Anomaly detection ─────────────────────────────────────────────────────────

def _build_anomalies(data: dict[str, Any]) -> list[str]:
    anomalies = []

    cpu = data.get("cpu") or {}
    ram = data.get("memory") or {}
    new_pids = data.get("new_process_pids", [])

    if cpu and cpu_anomaly(cpu.get("utilization_percent", 0)):
        anomalies.append(f"CPU at {cpu.get('utilization_percent')}%")

    if ram and ram_anomaly(_ram_percent(ram)):
        used = ram.get("in_use_gb", 0)
        total = ram.get("committed_total_gb", 0)
        anomalies.append(f"RAM at {used}GB / {total}GB used")

    disks = data.get("disks") or []
    for d in disks:
        r = d.get("read_kb_s", 0) / 1000
        w = d.get("write_kb_s", 0) / 1000
        if disk_anomaly(r, w):
            anomalies.append(f"Disk {d.get('disk_id')} I/O: {r+w:.1f}MB/s")
        active = d.get("active_time_percent")
        if active and active >= 95:
            anomalies.append(f"Disk {d.get('disk_id')} active time at {active}%")

    if process_spawned(new_pids):
        anomalies.append(f"New processes spawned: PIDs {new_pids}")

    gpu_list = data.get("gpu") or []
    for g in gpu_list:
        util = g.get("utilization_percent", 0)
        if util and util > 90:
            anomalies.append(f"GPU utilization at {util}%")

    # Disk space warnings
    disk_usage = data.get("disk_usage") or []
    for d in disk_usage:
        pct = d.get("percent_used", 0)
        if pct and pct >= 90:
            anomalies.append(f"Drive {d.get('mountpoint')} at {pct}% used ({d.get('free_gb', 0):.1f}GB free)")

    services = data.get("services") or []
    stopped_critical = [
        s["name"] for s in services
        if s.get("status") == "Stopped"
        and s.get("start_type") in ("Automatic", "Boot", "System")
        and s.get("name")
    ]
    if stopped_critical:
        anomalies.append(f"Auto-start services stopped: {stopped_critical[:3]}")

    return anomalies


def _ram_percent(ram: dict) -> float:
    used = ram.get("in_use_gb", 0) or 0
    total = ram.get("committed_total_gb", 1) or 1
    return round((used / total) * 100, 1)


# ── Narrative builder ─────────────────────────────────────────────────────────

def _build_narrative(
    data: dict[str, Any],
    anomalies: list[str],
    categories: list[str],
    prior: int,
) -> str:
    parts: list[str] = []

    # Disk free space summary
    disk_usage = data.get("disk_usage") or []
    if disk_usage:
        drive_lines = []
        for d in disk_usage:
            if "error" in d:
                continue
            drive_lines.append(
                f"{d.get('mountpoint')} — {d.get('free_gb', 0):.2f}GB free of {d.get('total_gb', 0):.2f}GB ({d.get('percent_used', 0):.1f}% used)"
            )
        if drive_lines:
            parts.append("Disk Space: " + " | ".join(drive_lines))

    # GPU summary
    gpu_static = data.get("gpu_static") or []
    gpu_live = data.get("gpu") or []
    if gpu_static:
        for g in gpu_static:
            vram = g.get("dedicated_vram_total_mb", "N/A")
            parts.append(f"GPU: {g.get('name', 'Unknown')} — VRAM {vram}MB total (driver {g.get('driver_version', 'N/A')})")
    elif gpu_live:
        for g in gpu_live:
            parts.append(f"GPU: utilization {g.get('utilization_percent', 0)}%, VRAM used {g.get('dedicated_vram_used_mb', 'N/A')}MB")

    # CPU/Memory summary if relevant
    if "performance" in categories or "resource" in categories:
        cpu = data.get("cpu") or {}
        mem = data.get("memory") or {}
        if cpu:
            parts.append(f"CPU: {cpu.get('utilization_percent', 'N/A')}% utilization")
        if mem:
            parts.append(f"RAM: {mem.get('in_use_gb', 'N/A')}GB used of {mem.get('committed_total_gb', 'N/A')}GB")

    # Anomalies
    if anomalies:
        procs = data.get("processes") or []
        top = _top_procs(procs)[0] if procs else None
        trigger = (
            f" Top process: {top.get('name', 'Unknown')} (PID {top.get('pid', 'N/A')}, CPU {top.get('cpu_percent', 0)}%)."
            if top else ""
        )
        prior_note = f" Pattern seen {prior}x before." if prior > 0 else ""
        parts.append(f"[ANOMALY] {'; '.join(anomalies)}.{trigger}{prior_note}")
    elif not parts:
        parts.append(f"System normal. Categories: {', '.join(categories)}.")

    return "\n".join(parts)


# ── Main compress entry point ─────────────────────────────────────────────────

def compress(
    data: dict[str, Any],
    categories: list[str],
    prior_occurrences: int = 0,
    intent: str = "",
) -> dict[str, Any]:
    # Normalise: accept single category string for backward compat
    if isinstance(categories, str):
        categories = [categories]

    category_label = categories[0] if categories else "unknown"

    if not data:
        return {
            "status": "insufficient_data",
            "categories": categories,
            "category": category_label,
            "narrative": "No data available yet. Polling may still be initializing.",
            "anomalies": [],
            "top_processes": [],
            "prior_occurrences": prior_occurrences,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "token_estimate": 20,
        }

    anomalies = _build_anomalies(data)
    status = "anomaly" if anomalies else "normal"
    narrative = _build_narrative(data, anomalies, categories, prior_occurrences)

    # Game compatibility check
    game_compat = None
    if intent:
        game_compat = _game_compat_check(intent, data)
        if game_compat:
            narrative = narrative + "\n\n" + game_compat if narrative else game_compat

    procs = _top_procs(data.get("processes") or [])
    token_est = _tokens(narrative + str(anomalies) + str(procs))

    result = {
        "status": status,
        "categories": categories,
        "category": category_label,
        "narrative": narrative,
        "anomalies": anomalies,
        "top_processes": procs,
        "prior_occurrences": prior_occurrences,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "token_estimate": token_est,
    }

    if game_compat:
        result["game_compatibility"] = game_compat

    # Include disk_usage directly in output when present
    if data.get("disk_usage"):
        result["disk_usage"] = data["disk_usage"]

    # Include gpu_static directly in output when present
    if data.get("gpu_static"):
        result["gpu_static"] = data["gpu_static"]

    return result
