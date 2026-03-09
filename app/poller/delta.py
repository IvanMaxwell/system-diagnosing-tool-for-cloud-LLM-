from typing import Any
from app.config import CONFIG


def _cpu_changed(prev: dict, curr: dict) -> bool:
    try:
        diff = abs(curr.get("utilization_percent", 0) - prev.get("utilization_percent", 0))
        return diff >= CONFIG.thresholds.cpu_delta_min
    except Exception:
        return True


def _ram_changed(prev: dict, curr: dict) -> bool:
    try:
        return prev.get("in_use_gb") != curr.get("in_use_gb")
    except Exception:
        return True


def _disk_changed(prev: list, curr: list) -> bool:
    try:
        def total_io(disks):
            if not disks:
                return 0
            d = disks[0]
            return d.get("read_kb_s", 0) + d.get("write_kb_s", 0)
        return total_io(prev) != total_io(curr)
    except Exception:
        return True


def _network_changed(prev: list, curr: list) -> bool:
    try:
        def total_traffic(adapters):
            if not adapters:
                return 0
            a = adapters[0]
            return a.get("send_kb_s", 0) + a.get("recv_kb_s", 0)
        return total_traffic(prev) != total_traffic(curr)
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

    if _ram_changed(previous.get("memory", {}), current.get("memory", {})):
        delta["memory"] = current["memory"]

    if _disk_changed(previous.get("disks", []), current.get("disks", [])):
        delta["disks"] = current["disks"]

    if _network_changed(previous.get("network", []), current.get("network", [])):
        delta["network"] = current["network"]

    # processes only exist in Tier2 merged state, not in every Tier1 live snapshot
    prev_pids = _process_pids(previous.get("processes") or [])
    curr_pids = _process_pids(current.get("processes") or [])
    new_pids = curr_pids - prev_pids

    if "processes" in current:
        delta["processes"] = current["processes"]
    delta["new_process_pids"] = list(new_pids)

    if "os_info" not in previous:
        delta["os_info"] = current.get("os_info", {})

    return delta
