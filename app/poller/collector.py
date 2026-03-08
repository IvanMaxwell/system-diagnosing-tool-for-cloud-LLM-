import platform
import psutil  # system metrics collection
from datetime import datetime, timezone
from typing import Any


def collect_cpu() -> dict[str, Any]:
    try:
        return {
            "percent_overall": psutil.cpu_percent(interval=0.1),
            "percent_per_core": psutil.cpu_percent(interval=0.1, percpu=True),
            "count_logical": psutil.cpu_count(logical=True),
            "count_physical": psutil.cpu_count(logical=False),
        }
    except Exception as e:
        return {"error": str(e)}


def collect_ram() -> dict[str, Any]:
    try:
        vm = psutil.virtual_memory()
        return {
            "total_gb": round(vm.total / 1e9, 2),
            "used_gb": round(vm.used / 1e9, 2),
            "percent": vm.percent,
        }
    except Exception as e:
        return {"error": str(e)}


def collect_disk_io() -> dict[str, Any]:
    try:
        io = psutil.disk_io_counters()
        if io is None:
            return {"read_mbps": 0.0, "write_mbps": 0.0}
        return {
            "read_mbps": round(io.read_bytes / 1e6, 2),
            "write_mbps": round(io.write_bytes / 1e6, 2),
        }
    except Exception as e:
        return {"error": str(e)}


def collect_network() -> dict[str, Any]:
    try:
        net = psutil.net_io_counters()
        return {
            "bytes_sent_mb": round(net.bytes_sent / 1e6, 2),
            "bytes_recv_mb": round(net.bytes_recv / 1e6, 2),
        }
    except Exception as e:
        return {"error": str(e)}


def collect_processes() -> list[dict[str, Any]]:
    try:
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append({
                    "pid": p.info["pid"],
                    "name": p.info["name"],
                    "cpu_percent": round(p.info["cpu_percent"] or 0.0, 2),
                    "memory_percent": round(p.info["memory_percent"] or 0.0, 2),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return sorted(procs, key=lambda x: x["cpu_percent"], reverse=True)[:20]
    except Exception as e:
        return [{"error": str(e)}]


def collect_os_info() -> dict[str, Any]:
    try:
        return {
            "system": platform.system(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
        }
    except Exception as e:
        return {"error": str(e)}


def collect_snapshot() -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu": collect_cpu(),
        "ram": collect_ram(),
        "disk_io": collect_disk_io(),
        "network": collect_network(),
        "processes": collect_processes(),
        "os_info": collect_os_info(),
    }
