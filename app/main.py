import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import CONFIG
from app.memory.store import init_db, write_event, get_recent_events, count_prior_occurrences
from app.poller.engine import start_polling, get_latest_snapshot, is_polling_active
from app.retrieval.intent import classify_intent, has_game_compat_check
from app.retrieval.fetcher import fetch_for_category, fetch_for_categories
from app.ssc.compressor import compress
from app.dqe.prompt import build_dqe_prompt, build_rejection_prompt
from app.dqe.sandbox import run_static_filter, execute_sandboxed, SafetyFilterError
from app.dqe.approval import store_pending, consume_pending, build_approval_response

# Logging setup
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=CONFIG.log_level,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(CONFIG.log_file),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await start_polling()
    logger.info("Service started")
    yield
    logger.info("Service shutting down")


app = FastAPI(
    title="System Diagnostics API",
    description="Token-efficient system diagnostics for cloud LLMs.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _verify_key(x_api_key: str = Header(...)) -> None:
    if x_api_key != CONFIG.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Request models ────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    intent: str
    model: str = "generic"
    use_ssc: bool = False


class DynamicSubmitRequest(BaseModel):
    code: str
    explanation: str


class DynamicExecuteRequest(BaseModel):
    approval_token: str


# ── Error handler ─────────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"status": "error", "code": "internal_error", "message": "Internal server error"},
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health(x_api_key: str = Header(...)) -> dict[str, Any]:
    _verify_key(x_api_key)
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "polling_active": is_polling_active(),
        "polling_interval_seconds": CONFIG.polling.interval_seconds,
        "dqe_enabled": CONFIG.dqe.enabled,
        "version": "1.0.0",
    }


@app.get("/snapshot")
async def snapshot(x_api_key: str = Header(...)) -> dict[str, Any]:
    _verify_key(x_api_key)
    snap = get_latest_snapshot()
    if not snap:
        return {"status": "error", "code": "no_data", "message": "No snapshot yet"}
    return snap


@app.post("/query")
async def query(body: QueryRequest, x_api_key: str = Header(...)) -> dict[str, Any]:
    _verify_key(x_api_key)

    categories = classify_intent(body.intent)

    if categories == ["no_match"]:
        if not CONFIG.dqe.enabled:
            return {
                "status": "no_match",
                "code": "intent_unmatched",
                "message": "Intent did not match any category. Enable DQE in config.yaml to handle custom queries.",
                "dqe_prompt": build_dqe_prompt(body.intent) if CONFIG.dqe.enabled else None,
            }
        return {
            "status": "dqe_required",
            "message": "Intent unmatched. Use /query/dynamic with the prompt below.",
            "dqe_prompt": build_dqe_prompt(body.intent),
        }

    snap = get_latest_snapshot()
    if not snap:
        return {"status": "error", "code": "no_data", "message": "Polling not ready yet"}

    # If query asks about game compatibility, also pull in hardware + gpu + resource
    if has_game_compat_check(body.intent):
        for extra in ("gpu", "resource", "hardware"):
            if extra not in categories:
                categories.append(extra)

    relevant = fetch_for_categories(snap, categories)
    
    if not body.use_ssc:
        # Return raw data without narrative compression
        return {
            "status": "raw",
            "categories": categories,
            "data": relevant
        }

    prior = count_prior_occurrences(categories[0])
    result = compress(relevant, categories, prior, intent=body.intent)

    top_proc = result["top_processes"][0].get("name", "Unknown") if result.get("top_processes") else ""
    write_event(body.intent, categories[0], result.get("narrative", ""), top_proc)

    return result


@app.get("/memory/recent")
async def memory_recent(x_api_key: str = Header(...)) -> dict[str, Any]:
    _verify_key(x_api_key)
    events = get_recent_events(10)
    return {"events": events, "count": len(events)}


@app.post("/query/dynamic")
async def query_dynamic(
    body: DynamicSubmitRequest, x_api_key: str = Header(...)
) -> dict[str, Any]:
    _verify_key(x_api_key)

    if not CONFIG.dqe.enabled:
        return {"status": "error", "code": "dqe_disabled", "message": "DQE is disabled in config.yaml"}

    try:
        run_static_filter(body.code)
    except SafetyFilterError as e:
        return {
            "status": "rejected",
            "code": "safety_filter_failed",
            "reason": str(e),
            "retry_prompt": build_rejection_prompt(str(e)),
        }

    token = store_pending(body.code, body.explanation)
    return build_approval_response(token, body.code, body.explanation)


@app.post("/query/dynamic/execute")
async def query_dynamic_execute(
    body: DynamicExecuteRequest, x_api_key: str = Header(...)
) -> dict[str, Any]:
    _verify_key(x_api_key)

    if not CONFIG.dqe.enabled:
        return {"status": "error", "code": "dqe_disabled", "message": "DQE is disabled in config.yaml"}

    entry = consume_pending(body.approval_token)
    if not entry:
        return {"status": "error", "code": "invalid_token", "message": "Token invalid or expired"}

    exec_result = execute_sandboxed(entry["code"])

    if not exec_result["success"]:
        write_event("dqe_execution", "unknown", f"DQE failed: {exec_result['error']}", dqe_used=True)
        return {"status": "error", "code": "execution_failed", "message": exec_result["error"]}

    snap = get_latest_snapshot()
    result = compress(snap or {}, "unknown", 0)
    result["dqe_output"] = exec_result["output"]

    write_event("dqe_execution", "unknown", result["narrative"], dqe_used=True)
    return result
