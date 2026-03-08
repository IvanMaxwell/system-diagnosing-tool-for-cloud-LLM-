from typing import Any

from app.retrieval.intent import IntentCategory


def fetch_for_category(
    snapshot: dict[str, Any], category: IntentCategory
) -> dict[str, Any]:
    if category == "performance":
        return {
            "cpu": snapshot.get("cpu", {}),
            "processes": snapshot.get("processes", [])[:5],
            "new_process_pids": snapshot.get("new_process_pids", []),
        }

    if category == "process":
        return {
            "processes": snapshot.get("processes", []),
            "new_process_pids": snapshot.get("new_process_pids", []),
        }

    if category == "resource":
        return {
            "ram": snapshot.get("ram", {}),
            "disk_io": snapshot.get("disk_io", {}),
            "network": snapshot.get("network", {}),
        }

    if category == "hardware":
        return {
            "os_info": snapshot.get("os_info", {}),
            "cpu": {
                "count_logical": snapshot.get("cpu", {}).get("count_logical"),
                "count_physical": snapshot.get("cpu", {}).get("count_physical"),
            },
            "ram": {"total_gb": snapshot.get("ram", {}).get("total_gb")},
        }

    return {}
