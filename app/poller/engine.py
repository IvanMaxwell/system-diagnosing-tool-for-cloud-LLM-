import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.config import CONFIG
from app.poller.collector import collect_snapshot
from app.poller.delta import compute_delta

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent.parent / "state" / "snapshot.json"
MAX_BYTES = CONFIG.polling.snapshot_max_kb * 1024

_latest_snapshot: dict[str, Any] = {}
_previous_snapshot: dict[str, Any] = {}
_polling_active: bool = False


def get_latest_snapshot() -> dict[str, Any]:
    return _latest_snapshot


def is_polling_active() -> bool:
    return _polling_active


def _load_state() -> list[dict]:
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"State load failed: {e}")
    return []


def _save_state(entries: list[dict]) -> None:
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


async def _poll_loop() -> None:
    global _latest_snapshot, _previous_snapshot, _polling_active
    _polling_active = True
    entries = _load_state()

    while True:
        try:
            current = collect_snapshot()
            delta = compute_delta(_previous_snapshot, current)
            _previous_snapshot = current
            _latest_snapshot = current
            entries.append(delta)
            _save_state(entries)
        except Exception as e:
            logger.error(f"Poll cycle failed: {e}")

        await asyncio.sleep(CONFIG.polling.interval_seconds)


async def start_polling() -> None:
    asyncio.create_task(_poll_loop())
    logger.info(f"Polling started — interval: {CONFIG.polling.interval_seconds}s")
