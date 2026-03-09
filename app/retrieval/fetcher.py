from typing import Any
from app.retrieval.intent import IntentCategory


def fetch_for_category(snapshot: dict[str, Any], category: IntentCategory) -> dict[str, Any]:
    if category == "performance":
        return {
            "cpu": snapshot.get("cpu"),
            "memory": {k: v for k, v in (snapshot.get("memory") or {}).items()
                       if k in ("in_use_gb", "available_gb", "cached_gb", "committed_total_gb")},
            "processes": (snapshot.get("processes") or [])[:5],
            "new_process_pids": snapshot.get("new_process_pids", []),
        }

    if category == "process":
        return {
            "processes": snapshot.get("processes", []),
            "new_process_pids": snapshot.get("new_process_pids", []),
        }

    if category == "resource":
        return {
            "memory": snapshot.get("memory"),
            "memory_static": snapshot.get("memory_static"),
            "disks": snapshot.get("disks"),
            "disk_usage": snapshot.get("disk_usage"),   # free/used/total per partition
            "network": snapshot.get("network"),
        }

    if category == "hardware":
        return {
            "cpu_static": snapshot.get("cpu_static"),
            "memory_static": snapshot.get("memory_static"),
            "disk_static": snapshot.get("disk_static"),
            "gpu_static": snapshot.get("gpu_static"),
        }

    if category == "gpu":
        return {
            "gpu": snapshot.get("gpu"),
            "gpu_static": snapshot.get("gpu_static"),
        }

    if category == "network":
        return {
            "network": snapshot.get("network"),
        }

    if category == "services":
        return {
            "services": snapshot.get("services", []),
        }

    if category == "app_history":
        return {
            "app_history": snapshot.get("app_history", []),
        }

    return {}


def fetch_for_categories(snapshot: dict[str, Any], categories: list[str]) -> dict[str, Any]:
    """Merge data from multiple categories into one dict."""
    merged: dict[str, Any] = {}
    for cat in categories:
        if cat == "no_match":
            continue
        data = fetch_for_category(snapshot, cat)  # type: ignore
        for k, v in data.items():
            if k not in merged:
                merged[k] = v
    return merged
