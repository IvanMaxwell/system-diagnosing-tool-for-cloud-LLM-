import hashlib
import time
from typing import Any

# In-memory pending approvals store — keyed by approval_token
_pending: dict[str, dict[str, Any]] = {}
APPROVAL_TTL_SECONDS = 300


def store_pending(code: str, explanation: str) -> str:
    token = hashlib.sha256(f"{code}{time.time()}".encode()).hexdigest()[:16]
    _pending[token] = {
        "code": code,
        "explanation": explanation,
        "created_at": time.time(),
    }
    return token


def retrieve_pending(token: str) -> dict[str, Any] | None:
    entry = _pending.get(token)
    if entry is None:
        return None
    if time.time() - entry["created_at"] > APPROVAL_TTL_SECONDS:
        del _pending[token]
        return None
    return entry


def consume_pending(token: str) -> dict[str, Any] | None:
    entry = retrieve_pending(token)
    if entry:
        del _pending[token]
    return entry


def build_approval_response(token: str, code: str, explanation: str) -> dict[str, Any]:
    return {
        "status": "awaiting_approval",
        "approval_token": token,
        "explanation": explanation,
        "code": code,
        "message": "Review the explanation and code above. POST approval_token to /query/dynamic/execute to run.",
    }
