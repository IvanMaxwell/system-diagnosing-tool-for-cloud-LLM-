"""
engine.py — 3-tier polling loop.
Tier 1: every 5s  — live metrics (cpu, memory, disk, network, gpu)
Tier 2: every 30s — processes, services, app history
Tier 3: once      — static hardware metadata
All tiers merged into a single state object. Delta-only writes to snapshot.json.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from app.config import CONFIG
from app.poller.collector import collect_live, collect_medium, collect_static
from app.poller.delta import compute_delta

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent.parent / "state" / "snapshot.json"
MAX_BYTES = CONFIG.polling.snapshot_max_kb * 1024

# In-memory merged state
_state: dict[str, Any] = {}
_polling_active: bool = False
_static_collected: bool = False


def get_latest_snapshot() -> dict[str, Any]:
    return _state.copy()


def is_polling_active() -> bool:
    return _polling_active


def _load_history() -> list[dict]:
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"State load failed: {e}")
    return []


def _save_history(entries: list[dict]) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(entries, indent=2)
        while len(raw.encode()) > MAX_BYTES and entries:
            entries.pop(0)
            raw = json.dumps(entries, indent=2)
        with open(STATE_FILE, "w") as f:
            f.write(raw)
    except Exception as e:
        logger.error(f"State save failed: {e}")


async def _tier1_loop(history: list[dict]) -> None:
    """Every 5s — live fast metrics."""
    global _state
    previous_live: dict[str, Any] = {}
    while True:
        try:
            live = collect_live()
            delta = compute_delta(previous_live, live)
            previous_live = live
            _state.update(live)
            history.append({"tier": 1, **delta})
            _save_history(history)
        except Exception as e:
            logger.error(f"Tier1 poll failed: {e}")
        await asyncio.sleep(CONFIG.polling.interval_seconds)


async def _tier2_loop() -> None:
    """Every 30s — processes, services, app history."""
    global _state
    while True:
        try:
            medium = collect_medium()
            _state.update(medium)
            logger.debug("Tier2 collected: processes/services/app_history")
        except Exception as e:
            logger.error(f"Tier2 poll failed: {e}")
        await asyncio.sleep(30)


async def _tier3_once() -> None:
    """Once on startup — static hardware metadata."""
    global _state, _static_collected
    try:
        static = collect_static()
        _state.update(static)
        _static_collected = True
        logger.info("Tier3 static hardware metadata collected")
    except Exception as e:
        logger.error(f"Tier3 static collection failed: {e}")


async def start_polling() -> None:
    global _polling_active
    history = _load_history()
    _polling_active = True
    # Tier 3 runs once immediately at startup
    asyncio.create_task(_tier3_once())
    # Tier 2 starts with a short delay to avoid startup spike
    await asyncio.sleep(2)
    asyncio.create_task(_tier2_loop())
    # Tier 1 is the main loop
    asyncio.create_task(_tier1_loop(history))
    logger.info(
        f"Polling started — T1:{CONFIG.polling.interval_seconds}s T2:30s T3:once"
    )
