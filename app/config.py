import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List


@dataclass
class PollingConfig:
    interval_seconds: int = 5
    lite_interval_seconds: int = 15
    snapshot_max_kb: int = 500


@dataclass
class ThresholdConfig:
    cpu_percent: float = 75.0
    ram_percent: float = 85.0
    disk_io_mbps: float = 200.0
    cpu_delta_min: float = 2.0
    process_spawn_window_seconds: int = 10


@dataclass
class DQEConfig:
    enabled: bool = False
    execution_timeout_seconds: int = 5
    approved_imports: List[str] = field(default_factory=lambda: [
        "psutil", "os", "platform", "subprocess", "json", "datetime"
    ])


@dataclass
class AppConfig:
    api_key: str = "change-me-before-use"
    polling: PollingConfig = field(default_factory=PollingConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    dqe: DQEConfig = field(default_factory=DQEConfig)
    db_path: str = "app/state/memory.db"
    log_level: str = "INFO"
    log_file: str = "logs/service.log"


def load_config() -> AppConfig:
    config_path = Path(__file__).parent.parent / "config.yaml"
    if not config_path.exists():
        return AppConfig()
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)
    polling = PollingConfig(**raw.get("polling", {}))
    thresholds = ThresholdConfig(**raw.get("thresholds", {}))
    dqe_raw = raw.get("dqe", {})
    dqe = DQEConfig(
        enabled=dqe_raw.get("enabled", False),
        execution_timeout_seconds=dqe_raw.get("execution_timeout_seconds", 5),
        approved_imports=dqe_raw.get("approved_imports", DQEConfig().approved_imports),
    )
    mem = raw.get("memory", {})
    log = raw.get("logging", {})
    return AppConfig(
        api_key=raw.get("api_key", "change-me-before-use"),
        polling=polling,
        thresholds=thresholds,
        dqe=dqe,
        db_path=mem.get("db_path", "app/state/memory.db"),
        log_level=log.get("level", "INFO"),
        log_file=log.get("file", "logs/service.log"),
    )


CONFIG: AppConfig = load_config()
