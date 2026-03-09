from typing import Literal

INTENT_MAP: dict[str, list[str]] = {
    # specific categories first to prevent keyword conflicts
    "gpu":          ["gpu", "graphics", "vram", "video card", "render", "directx", "cuda", "graphics card"],
    "services":     ["service", "services", "windows service", "daemon", "background service", "svchost", "running service", "stopped service", "wuauserv", "spooler", "svc"],
    "app_history":  ["app history", "usage history", "most used", "application usage", "top apps", "per app", "app usage", "which app", "apps use"],
    "network":      ["wifi", "ethernet", "ip address", "dns", "adapter", "signal strength", "connection speed", "net adapter"],
    "hardware":     ["hardware", "specs", "system info", "form factor", "slots", "cpu info", "bios", "motherboard"],
    "process":      ["process", "pid", "kill", "executable", "spawned", "task manager process"],
    "resource":     ["memory", "ram", "disk", "storage", "disk io", "bandwidth", "space", "io usage", "free", "hard drive", "ssd", "hdd", "drive"],
    "performance":  ["slow", "lag", "freeze", "performance", "speed", "fast", "stuck", "unresponsive", "cpu", "usage", "network", "running"],
}

# Keywords that trigger a game/software compatibility check
GAME_COMPAT_KEYWORDS = [
    "can i run", "can i play", "will it run", "run rdr2", "run gta", "run cyberpunk",
    "run fortnite", "run minecraft", "play rdr2", "play gta", "play cyberpunk",
    "download rdr2", "download gta", "can my pc", "can my computer", "my pc run",
    "requirements", "game requirements", "compatible", "game ready",
]

IntentCategory = Literal[
    "performance", "process", "resource", "hardware",
    "gpu", "network", "services", "app_history", "no_match"
]


def classify_intent(intent: str) -> list[IntentCategory]:
    """Returns a list of all matched categories for a given intent string."""
    lowered = intent.lower()
    matched: list[IntentCategory] = []
    for category, keywords in INTENT_MAP.items():
        if any(kw in lowered for kw in keywords):
            matched.append(category)  # type: ignore
    if not matched:
        return ["no_match"]
    return matched


def has_game_compat_check(intent: str) -> bool:
    """Returns True if the query is asking about running a specific game or app."""
    lowered = intent.lower()
    return any(kw in lowered for kw in GAME_COMPAT_KEYWORDS)
