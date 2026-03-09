"""
collector.py — Full Task Manager parity collector.
Requires admin elevation. All WMI calls wrapped in try/except.
Returns null + source flag on failure, never raises.
Tabs covered: CPU, Memory, Disk, Network, GPU, Processes, Services, App History.
"""
import socket
import platform
import psutil  # fast system metrics
from datetime import datetime, timezone
from typing import Any


# ── Helpers ────────────────────────────────────────────────────────────────────

def _gb(b: int) -> float:
    return round(b / 1e9, 2)

def _mb(b: int) -> float:
    return round(b / 1e6, 2)

def _kb(b: int) -> float:
    return round(b / 1e3, 2)

def _wmi(namespace: str = "root/cimv2"):
    try:
        import wmi  # windows management instrumentation — pip install wmi
        return wmi.WMI(namespace=namespace)
    except Exception:
        return None


# ── CPU ────────────────────────────────────────────────────────────────────────

def collect_cpu_live() -> dict[str, Any]:
    """Tier 1 — every 5s."""
    try:
        freq = psutil.cpu_freq()
        boot = psutil.boot_time()
        uptime_s = int(datetime.now(timezone.utc).timestamp() - boot)
        h, rem = divmod(uptime_s, 3600)
        m, s = divmod(rem, 60)

        threads = 0
        handles = 0
        for p in psutil.process_iter(["num_threads", "num_handles"]):
            try:
                threads += p.info.get("num_threads") or 0
                handles += p.info.get("num_handles") or 0
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return {
            "utilization_percent": psutil.cpu_percent(interval=0.1),
            "current_speed_ghz": round(freq.current / 1000, 2) if freq else None,
            "processes": len(psutil.pids()),
            "threads": threads,
            "handles": handles,
            "uptime": f"{h:02d}:{m:02d}:{s:02d}",
        }
    except Exception as e:
        return {"error": str(e)}


def collect_cpu_static() -> dict[str, Any]:
    """Tier 3 — once on startup."""
    result: dict[str, Any] = {
        "name": platform.processor(),
        "base_speed_mhz": None,
        "sockets": None,
        "cores": psutil.cpu_count(logical=False),
        "logical_processors": psutil.cpu_count(logical=True),
        "virtualization": None,
        "l1_cache_kb": None,
        "l2_cache_kb": None,
        "l3_cache_kb": None,
    }
    c = _wmi()
    if not c:
        return result
    try:
        procs = c.Win32_Processor()
        if procs:
            p = procs[0]
            result["name"] = getattr(p, "Name", result["name"])
            result["base_speed_mhz"] = getattr(p, "MaxClockSpeed", None)
            result["sockets"] = len(procs)
            result["virtualization"] = bool(getattr(p, "VirtualizationFirmwareEnabled", False))
            result["l2_cache_kb"] = getattr(p, "L2CacheSize", None)
            result["l3_cache_kb"] = getattr(p, "L3CacheSize", None)
    except Exception:
        pass
    try:
        for cache in c.Win32_CacheMemory():
            if getattr(cache, "Level", None) == 3:
                result["l1_cache_kb"] = getattr(cache, "MaxCacheSize", None)
    except Exception:
        pass
    return result


# ── Memory ─────────────────────────────────────────────────────────────────────

def collect_memory_live() -> dict[str, Any]:
    """Tier 1 — every 5s."""
    try:
        vm = psutil.virtual_memory()
        result: dict[str, Any] = {
            "in_use_gb": _gb(vm.used),
            "available_gb": _gb(vm.available),
            "committed_used_gb": _gb(vm.used),
            "committed_total_gb": _gb(vm.total),
            "cached_gb": _gb(getattr(vm, "cached", 0) or 0),
            "compressed_mb": None,
            "paged_pool_mb": None,
            "non_paged_pool_mb": None,
        }
    except Exception as e:
        return {"error": str(e)}

    c = _wmi()
    if not c:
        return result
    try:
        perf = c.Win32_PerfFormattedData_PerfOS_Memory()
        if perf:
            p = perf[0]
            result["paged_pool_mb"] = _mb(int(getattr(p, "PoolPagedBytes", 0) or 0))
            result["non_paged_pool_mb"] = _mb(int(getattr(p, "PoolNonpagedBytes", 0) or 0))
            result["cached_gb"] = _gb(int(getattr(p, "CacheBytes", 0) or 0))
            result["compressed_mb"] = _mb(int(getattr(p, "SystemCacheResidentBytes", 0) or 0))
    except Exception:
        pass
    return result


def collect_memory_static() -> dict[str, Any]:
    """Tier 3 — once on startup."""
    form_factor_map = {
        0: "Unknown", 7: "SIMM", 8: "DIMM", 9: "TSOP",
        12: "SODIMM", 13: "SRIMM", 22: "FPBGA", 23: "LGA",
    }
    result: dict[str, Any] = {
        "speed_mhz": None,
        "slots_used": None,
        "slots_total": None,
        "form_factor": None,
        "hardware_reserved_mb": None,
    }
    c = _wmi()
    if not c:
        return result
    try:
        sticks = c.Win32_PhysicalMemory()
        if sticks:
            result["slots_used"] = len(sticks)
            result["speed_mhz"] = getattr(sticks[0], "Speed", None)
            ff = int(getattr(sticks[0], "FormFactor", 0) or 0)
            result["form_factor"] = form_factor_map.get(ff, "Unknown")
    except Exception:
        pass
    try:
        arrays = c.Win32_PhysicalMemoryArray()
        if arrays:
            result["slots_total"] = getattr(arrays[0], "MemoryDevices", None)
    except Exception:
        pass
    try:
        perf = c.Win32_PerfFormattedData_PerfOS_Memory()
        if perf:
            reserved = getattr(perf[0], "FreeAndZeroPageListBytes", None)
            result["hardware_reserved_mb"] = _mb(int(reserved)) if reserved else None
    except Exception:
        pass
    return result


# ── Disk ───────────────────────────────────────────────────────────────────────

def collect_disk_usage() -> list[dict[str, Any]]:
    """Collect free/used/total space per mounted partition."""
    partitions: list[dict[str, Any]] = []
    try:
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "mountpoint": part.mountpoint,
                    "device": part.device,
                    "fstype": part.fstype,
                    "total_gb": _gb(usage.total),
                    "used_gb": _gb(usage.used),
                    "free_gb": _gb(usage.free),
                    "percent_used": usage.percent,
                })
            except (PermissionError, OSError):
                continue
    except Exception as e:
        return [{"error": str(e)}]
    return partitions


def collect_disk_live() -> list[dict[str, Any]]:
    """Tier 1 — every 5s."""
    disks: list[dict[str, Any]] = []
    try:
        io = psutil.disk_io_counters(perdisk=True) or {}
        for name, ctr in io.items():
            disks.append({
                "disk_id": name,
                "read_kb_s": _kb(ctr.read_bytes),
                "write_kb_s": _kb(ctr.write_bytes),
                "active_time_percent": None,
                "avg_response_time_ms": None,
            })
    except Exception as e:
        return [{"error": str(e)}]

    c = _wmi()
    if not c:
        return disks
    try:
        for p in c.Win32_PerfFormattedData_PerfDisk_PhysicalDisk():
            name = getattr(p, "Name", "")
            if name == "_Total":
                continue
            active = getattr(p, "PercentDiskTime", None)
            resp = getattr(p, "AvgDiskSecPerTransfer", None)
            for d in disks:
                if d["disk_id"] in name or name in d["disk_id"]:
                    d["active_time_percent"] = int(active) if active else None
                    d["avg_response_time_ms"] = round(float(resp) * 1000, 2) if resp else None
    except Exception:
        pass
    return disks


def collect_disk_static() -> list[dict[str, Any]]:
    """Tier 3 — once on startup."""
    disks: list[dict[str, Any]] = []
    c = _wmi()
    if not c:
        return disks
    media_map = {3: "HDD", 4: "SSD", 5: "SCM"}
    try:
        for d in c.Win32_DiskDrive():
            disks.append({
                "model": getattr(d, "Model", None),
                "capacity_gb": _gb(int(getattr(d, "Size", 0) or 0)),
                "formatted_gb": None,
                "system_disk": False,
                "pagefile": False,
                "type": None,
                "drive_letters": [],
            })
    except Exception:
        pass

    try:
        ns = _wmi("root/Microsoft/Windows/Storage")
        if ns:
            for i, p in enumerate(ns.MSFT_PhysicalDisk()):
                mt = int(getattr(p, "MediaType", 0) or 0)
                if i < len(disks):
                    disks[i]["type"] = media_map.get(mt, "Unknown")
    except Exception:
        pass

    try:
        for ld in c.Win32_LogicalDisk():
            letter = getattr(ld, "DeviceID", "")
            size = getattr(ld, "Size", None)
            for d in disks:
                if letter not in d["drive_letters"]:
                    d["drive_letters"].append(letter)
                if size:
                    d["formatted_gb"] = _gb(int(size))
                if letter == "C:":
                    d["system_disk"] = True
        for pf in c.Win32_PageFileUsage():
            pf_name = getattr(pf, "Name", "")
            for d in disks:
                if any(letter in pf_name for letter in d["drive_letters"]):
                    d["pagefile"] = True
    except Exception:
        pass
    return disks


# ── Network ────────────────────────────────────────────────────────────────────

def collect_network_live() -> list[dict[str, Any]]:
    """Tier 1 — every 5s."""
    adapters: list[dict[str, Any]] = []
    try:
        stats = psutil.net_io_counters(pernic=True) or {}
        addrs = psutil.net_if_addrs()
        import socket as _sock

        for nic, ctr in stats.items():
            ipv4, ipv6 = None, None
            for addr in addrs.get(nic, []):
                if addr.family == _sock.AF_INET:
                    ipv4 = addr.address
                elif addr.family == _sock.AF_INET6:
                    ipv6 = addr.address
            adapters.append({
                "adapter": nic,
                "send_kb_s": _kb(ctr.bytes_sent),
                "recv_kb_s": _kb(ctr.bytes_recv),
                "ipv4": ipv4,
                "ipv6": ipv6,
                "dns_name": None,
                "signal_strength_dbm": None,
                "connection_type": None,
                "speed_mbps": None,
            })
        try:
            dns = socket.getfqdn()
            for a in adapters:
                a["dns_name"] = dns
        except Exception:
            pass
    except Exception as e:
        return [{"error": str(e)}]

    c = _wmi()
    if c:
        try:
            for wa in c.Win32_NetworkAdapter(PhysicalAdapter=True):
                conn_id = getattr(wa, "NetConnectionID", "") or ""
                speed = getattr(wa, "Speed", None)
                atype = getattr(wa, "AdapterType", None)
                for a in adapters:
                    if conn_id and conn_id in a["adapter"]:
                        a["speed_mbps"] = round(int(speed) / 1e6) if speed else None
                        a["connection_type"] = atype
        except Exception:
            pass
        try:
            wifi_ns = _wmi("root/WMI")
            if wifi_ns:
                for sig in wifi_ns.MSNdis_80211_ReceivedSignalStrength():
                    val = getattr(sig, "Ndis80211ReceivedSignalStrength", None)
                    inst = getattr(sig, "InstanceName", "")
                    for a in adapters:
                        if inst and inst in a["adapter"]:
                            a["signal_strength_dbm"] = val
        except Exception:
            pass
    return adapters


# ── GPU ────────────────────────────────────────────────────────────────────────

def collect_gpu_live() -> list[dict[str, Any]]:
    """Tier 1 — every 5s. Requires admin for engine breakdown."""
    gpus: list[dict[str, Any]] = []
    c = _wmi()
    if c:
        try:
            gpu_map: dict[str, dict] = {}
            for e in c.Win32_PerfFormattedData_GPUEngine_GPUEngine():
                name = getattr(e, "Name", "") or ""
                util = int(getattr(e, "UtilizationPercentage", 0) or 0)
                parts = name.split("_")
                gpu_idx = next((p for p in parts if "luid" in p.lower()), "gpu0")
                eng_type = next((p for p in parts if "engtype" in p.lower()), "")
                if gpu_idx not in gpu_map:
                    gpu_map[gpu_idx] = {
                        "gpu_index": gpu_idx,
                        "name": "Unknown GPU",
                        "utilization_percent": 0,
                        "engine_3d_percent": None,
                        "engine_copy_percent": None,
                        "engine_video_decode_percent": None,
                        "dedicated_vram_used_mb": None,
                        "shared_vram_used_mb": None,
                    }
                gpu_map[gpu_idx]["utilization_percent"] = max(
                    gpu_map[gpu_idx]["utilization_percent"], util
                )
                if "3D" in eng_type:
                    gpu_map[gpu_idx]["engine_3d_percent"] = util
                elif "Copy" in eng_type:
                    gpu_map[gpu_idx]["engine_copy_percent"] = util
                elif "VideoDecode" in eng_type or "VideoEncode" in eng_type:
                    gpu_map[gpu_idx]["engine_video_decode_percent"] = util
            gpus = list(gpu_map.values())
        except Exception:
            gpus = []

        try:
            vc_names = []
            for vc in c.Win32_VideoController():
                vc_names.append(getattr(vc, "Name", "Unknown GPU"))
            
            for i, m in enumerate(c.Win32_PerfFormattedData_GPUAdapterMemory_GPUAdapterMemory()):
                ded = getattr(m, "DedicatedUsage", None)
                shared = getattr(m, "SharedUsage", None)
                if i < len(gpus):
                    gpus[i]["dedicated_vram_used_mb"] = _mb(int(ded)) if ded else None
                    gpus[i]["shared_vram_used_mb"] = _mb(int(shared)) if shared else None
                    if i < len(vc_names):
                        gpus[i]["name"] = vc_names[i]
        except Exception:
            pass

    # Fallback to nvidia-smi if WMI counters failed or returned nothing
    if not gpus:
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            for i, line in enumerate(result.stdout.strip().split("\n")):
                if not line.strip():
                    continue
                parts = line.split(",")
                if len(parts) >= 3:
                    gpu_name = parts[0].strip()
                    util = int(parts[1].strip())
                    vram_used = int(parts[2].strip())
                    gpus.append({
                        "gpu_index": f"gpu{i}",
                        "name": gpu_name,
                        "utilization_percent": util,
                        "engine_3d_percent": None,
                        "engine_copy_percent": None,
                        "engine_video_decode_percent": None,
                        "dedicated_vram_used_mb": vram_used,
                        "shared_vram_used_mb": None,
                    })
        except Exception:
            pass

    return gpus

def collect_gpu_static() -> list[dict[str, Any]]:
    """Tier 3 — once on startup."""
    gpus: list[dict[str, Any]] = []
    c = _wmi()
    if not c:
        return gpus
    try:
        for vc in c.Win32_VideoController():
            ram = int(getattr(vc, "AdapterRAM", 0) or 0)
            if ram < 0:
                ram += 4294967296  # Fix 32-bit signed integer overflow for 4GB+ GPUs
            gpus.append({
                "name": getattr(vc, "Name", None),
                "driver_version": getattr(vc, "DriverVersion", None),
                "dedicated_vram_total_mb": _mb(ram),
                "pnp_device_id": getattr(vc, "PNPDeviceID", None),
            })
    except Exception:
        pass
    return gpus


# ── Processes ─────────────────────────────────────────────────────────────────

def collect_processes() -> list[dict[str, Any]]:
    """Tier 2 — every 30s. Details tab parity."""
    procs: list[dict[str, Any]] = []
    attrs = ["pid", "name", "status", "cpu_percent",
             "memory_percent", "memory_info", "num_threads", "username", "exe"]
    for p in psutil.process_iter(attrs):
        try:
            info = p.info
            mem = info.get("memory_info")
            procs.append({
                "pid": info.get("pid"),
                "name": info.get("name"),
                "status": info.get("status"),
                "cpu_percent": round(info.get("cpu_percent") or 0.0, 2),
                "memory_mb": _mb(mem.rss) if mem else None,
                "memory_percent": round(info.get("memory_percent") or 0.0, 2),
                "threads": info.get("num_threads"),
                "username": info.get("username"),
                "executable": info.get("exe"),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(procs, key=lambda x: x["cpu_percent"], reverse=True)[:50]


# ── Services ──────────────────────────────────────────────────────────────────

def collect_services() -> list[dict[str, Any]]:
    """Tier 2 — every 30s. Services tab parity."""
    state_map = {
        1: "Stopped", 2: "Start Pending", 3: "Stop Pending",
        4: "Running", 5: "Continue Pending", 6: "Pause Pending", 7: "Paused",
    }
    start_map = {0: "Boot", 1: "System", 2: "Automatic", 3: "Manual", 4: "Disabled"}
    services: list[dict[str, Any]] = []

    try:
        import win32service  # pywin32 — windows native service enumeration
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ENUMERATE_SERVICE)
        for svc in win32service.EnumServicesStatusEx(scm):
            services.append({
                "name": svc.get("ServiceName"),
                "display_name": svc.get("DisplayName"),
                "status": state_map.get(svc.get("CurrentState", 0), "Unknown"),
                "pid": svc.get("ProcessId") or None,
                "start_type": start_map.get(svc.get("StartType", 3), "Manual"),
            })
        win32service.CloseServiceHandle(scm)
        return services
    except ImportError:
        pass
    except Exception as e:
        return [{"error": str(e)}]

    # Fallback: sc query via subprocess
    try:
        import subprocess
        result = subprocess.run(
            ["sc", "query", "type=", "all", "state=", "all"],
            capture_output=True, text=True, timeout=5
        )
        current: dict[str, Any] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("SERVICE_NAME:"):
                if current:
                    services.append(current)
                current = {"name": line.split(":", 1)[1].strip(),
                           "display_name": None, "status": None,
                           "pid": None, "start_type": None}
            elif "STATE" in line and current:
                parts = line.split()
                current["status"] = parts[-1] if parts else None
        if current:
            services.append(current)
    except Exception as e:
        return [{"error": str(e)}]
    return services


# ── App History ───────────────────────────────────────────────────────────────

def collect_app_history() -> list[dict[str, Any]]:
    """Tier 2 — every 30s. App History tab via WMI perf counters."""
    apps: list[dict[str, Any]] = []
    c = _wmi()
    if not c:
        return apps
    try:
        seen: dict[str, dict] = {}
        for p in c.Win32_PerfFormattedData_PerfProc_Process():
            name = getattr(p, "Name", "") or ""
            if name in ("_Total", "Idle"):
                continue
            cpu_t = int(getattr(p, "PercentProcessorTime", 0) or 0)
            io_r = int(getattr(p, "IOReadBytesPerSec", 0) or 0)
            io_w = int(getattr(p, "IOWriteBytesPerSec", 0) or 0)
            net = int(getattr(p, "IOOtherBytesPerSec", 0) or 0)
            base = name.split("#")[0]  # merge chrome#1, chrome#2 → chrome
            if base not in seen:
                seen[base] = {
                    "name": base,
                    "cpu_time_percent": 0,
                    "network_mb": 0.0,
                    "disk_read_mb": 0.0,
                    "disk_write_mb": 0.0,
                }
            seen[base]["cpu_time_percent"] += cpu_t
            seen[base]["network_mb"] += _mb(net)
            seen[base]["disk_read_mb"] += _mb(io_r)
            seen[base]["disk_write_mb"] += _mb(io_w)
        apps = sorted(seen.values(), key=lambda x: x["cpu_time_percent"], reverse=True)[:30]
    except Exception as e:
        return [{"error": str(e)}]
    return apps


# ── Master collectors ──────────────────────────────────────────────────────────

def collect_live() -> dict[str, Any]:
    """Tier 1 — every 5s."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu": collect_cpu_live(),
        "memory": collect_memory_live(),
        "disks": collect_disk_live(),
        "disk_usage": collect_disk_usage(),
        "network": collect_network_live(),
        "gpu": collect_gpu_live(),
    }


def collect_medium() -> dict[str, Any]:
    """Tier 2 — every 30s."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "processes": collect_processes(),
        "services": collect_services(),
        "app_history": collect_app_history(),
    }


def collect_static() -> dict[str, Any]:
    """Tier 3 — once on startup."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu_static": collect_cpu_static(),
        "memory_static": collect_memory_static(),
        "disk_static": collect_disk_static(),
        "gpu_static": collect_gpu_static(),
    }
