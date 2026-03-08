from datetime import datetime, timezone
from typing import Any

from app.ssc.thresholds import cpu_anomaly, ram_anomaly, disk_anomaly, process_spawned


def _estimate_tokens(text: str) -> int:
    # rough approximation: 1 token ≈ 4 characters
    return max(1, len(text) // 4)


def _top_processes(processes: list[dict], n: int = 3) -> list[dict]:
    return sorted(processes, key=lambda p: p.get("cpu_percent", 0), reverse=True)[:n]


def _build_anomalies(snapshot: dict[str, Any]) -> list[str]:
    anomalies = []
    cpu = snapshot.get("cpu", {})
    ram = snapshot.get("ram", {})
    disk = snapshot.get("disk_io", {})
    new_pids = snapshot.get("new_process_pids", [])

    if cpu and cpu_anomaly(cpu.get("percent_overall", 0)):
        anomalies.append(
            f"CPU at {cpu.get('percent_overall')}% — exceeds {85} baseline threshold"
        )

    if ram and ram_anomaly(ram.get("percent", 0)):
        anomalies.append(
            f"RAM at {ram.get('percent')}% ({ram.get('used_gb')}GB used)"
        )

    if disk and disk_anomaly(disk.get("read_mbps", 0), disk.get("write_mbps", 0)):
        total = disk.get("read_mbps", 0) + disk.get("write_mbps", 0)
        anomalies.append(f"Disk I/O at {total:.1f}MB/s — sustained high load")

    if process_spawned(new_pids):
        anomalies.append(f"New processes spawned: PIDs {new_pids}")

    return anomalies


def _build_narrative(
    anomalies: list[str],
    top_procs: list[dict],
    prior_occurrences: int,
    category: str,
) -> str:
    if not anomalies:
        return f"System normal. Category: {category}."

    top = top_procs[0] if top_procs else None
    trigger = f" Likely trigger: {top['name']} (PID {top['pid']}, CPU {top['cpu_percent']}%)." if top else ""
    prior = f" Pattern seen {prior_occurrences}x before." if prior_occurrences > 0 else ""
    return f"[ANOMALY] {'; '.join(anomalies)}.{trigger}{prior}"


def compress(
    snapshot: dict[str, Any],
    category: str,
    prior_occurrences: int = 0,
) -> dict[str, Any]:
    anomalies = _build_anomalies(snapshot)
    top_procs = _top_processes(snapshot.get("processes", []))
    status = "anomaly" if anomalies else "normal"

    if not snapshot or snapshot == {}:
        status = "insufficient_data"

    narrative = _build_narrative(anomalies, top_procs, prior_occurrences, category)
    token_est = _estimate_tokens(narrative + str(anomalies) + str(top_procs))

    return {
        "status": status,
        "category": category,
        "narrative": narrative,
        "anomalies": anomalies,
        "top_processes": top_procs,
        "prior_occurrences": prior_occurrences,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "token_estimate": token_est,
    }
