from typing import Literal

INTENT_MAP: dict[str, list[str]] = {
    "performance": ["slow", "lag", "freeze", "cpu", "performance", "speed", "fast", "stuck"],
    "process": ["process", "running", "started", "spawned", "task", "app", "program", "kill"],
    "resource": ["memory", "ram", "disk", "full", "storage", "network", "bandwidth", "space"],
    "hardware": ["temperature", "battery", "os", "hardware", "specs", "system info", "machine", "version"],
}

IntentCategory = Literal["performance", "process", "resource", "hardware", "no_match"]


def classify_intent(intent: str) -> IntentCategory:
    lowered = intent.lower()
    for category, keywords in INTENT_MAP.items():
        if any(kw in lowered for kw in keywords):
            return category  # type: ignore
    return "no_match"
