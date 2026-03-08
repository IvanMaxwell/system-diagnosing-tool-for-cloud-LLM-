from typing import Any
from app.config import CONFIG


def _cpu_changed(prev: dict, curr: dict) -> bool:
    try:
        diff = abs(curr.get("percent_overall", 0) - prev.get("percent_overall", 0))
        return diff >= CONFIG.thresholds.cpu_delta_min
    except Exception:
        return True


def _ram_changed(prev: dict, curr: dict) -> bool:
    try:
        return prev.get("percent") != curr.get("percent")
    except Exception:
        return True


def _disk_changed(prev: dict, curr: dict) -> bool:
    try:
        return (
            prev.get("read_mbps") != curr.get("read_mbps")
            or prev.get("write_mbps") != curr.get("write_mbps")
        )
    except Exception:
        return True


def _network_changed(prev: dict, curr: dict) -> bool:
    try:
        return (
            prev.get("bytes_sent_mb") != curr.get("bytes_sent_mb")
            or prev.get("bytes_recv_mb") != curr.get("bytes_recv_mb")
        )
    except Exception:
        return True


def _process_pids(processes: list[dict]) -> set[int]:
    return {p["pid"] for p in processes if "pid" in p}


def compute_delta(
    previous: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    if not previous:
        return current

    delta: dict[str, Any] = {"timestamp": current["timestamp"]}

    if _cpu_changed(previous.get("cpu", {}), current.get("cpu", {})):
        delta["cpu"] = current["cpu"]

    if _ram_changed(previous.get("ram", {}), current.get("ram", {})):
        delta["ram"] = current["ram"]

    if _disk_changed(previous.get("disk_io", {}), current.get("disk_io", {})):
        delta["disk_io"] = current["disk_io"]

    if _network_changed(previous.get("network", {}), current.get("network", {})):
        delta["network"] = current["network"]

    prev_pids = _process_pids(previous.get("processes", []))
    curr_pids = _process_pids(current.get("processes", []))
    new_pids = curr_pids - prev_pids

    delta["processes"] = current["processes"]
    delta["new_process_pids"] = list(new_pids)

    if "os_info" not in previous:
        delta["os_info"] = current.get("os_info", {})

    return delta
