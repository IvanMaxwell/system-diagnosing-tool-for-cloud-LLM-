from app.config import CONFIG


def cpu_anomaly(cpu_percent: float) -> bool:
    return cpu_percent > CONFIG.thresholds.cpu_percent


def ram_anomaly(ram_percent: float) -> bool:
    return ram_percent > CONFIG.thresholds.ram_percent


def disk_anomaly(read_mbps: float, write_mbps: float) -> bool:
    return (read_mbps + write_mbps) > CONFIG.thresholds.disk_io_mbps


def process_spawned(new_pids: list[int]) -> bool:
    return len(new_pids) > 0


def get_threshold_summary() -> dict:
    return {
        "cpu_percent": CONFIG.thresholds.cpu_percent,
        "ram_percent": CONFIG.thresholds.ram_percent,
        "disk_io_mbps": CONFIG.thresholds.disk_io_mbps,
        "cpu_delta_min": CONFIG.thresholds.cpu_delta_min,
    }
