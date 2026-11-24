import asyncio
import hashlib
import json
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from . import db
from .config import settings
from .llm import ProviderError, call_with_key, parse_simulate_failure

app = FastAPI(title="Lyftr AI - LLM Chatbot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": str(exc.errors())})


@app.on_event("startup")
def on_startup():
    db.init_db()


class ChatRequest(BaseModel):
    session_id: str
    message: str
    system_prompt: str | None = None

    @field_validator("session_id")
    @classmethod
    def check_session(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 128):
            raise ValueError("session_id must be 1-128 chars")
        return v

    @field_validator("message")
    @classmethod
    def check_message(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 4000):
            raise ValueError("message must be 1-4000 chars after trimming")
        return v


@app.get("/health")
def health():
    db.init_db()
    # Verify DB is reachable
    conn = db.get_conn()
    try:
        conn.execute("SELECT 1").fetchone()
    finally:
        conn.close()
    return {
        "status": "ok",
        "keys_configured": len(settings.llm_api_keys),
        "cache_enabled": True,
    }


@app.post("/chat")
async def chat(payload: ChatRequest, x_simulate_failure: str | None = Header(default=None)):
    start = time.perf_counter()
    db.init_db()
    db.ensure_session(payload.session_id, payload.system_prompt)

    system_prompt = payload.system_prompt or db.get_system_prompt(payload.session_id) or settings.default_system_prompt
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in db.get_messages(payload.session_id)
    ]
    full_messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": payload.message}
    ]

    # --- Cache lookup: key = model + full message list ---------------------
    cache_key = hashlib.sha256(
        json.dumps({"model": settings.llm_model, "messages": full_messages}, sort_keys=True).encode()
    ).hexdigest()
    cached = db.cache_get(cache_key)
    if cached is not None:
        latency_ms = max(1, int((time.perf_counter() - start) * 1000))
        metadata = {
            "resolution_source": "LLM_CACHE",
            "model": cached["model"],
            "latency_ms": latency_ms,
            "input_tokens": cached["input_tokens"],
            "output_tokens": cached["output_tokens"],
            "key_id": None,
            "fallback_attempts": 0,
        }
        db.add_message(payload.session_id, "user", payload.message)
        db.add_message(payload.session_id, "assistant", cached["reply"], metadata)
        return {"session_id": payload.session_id, "reply": cached["reply"], "metadata": metadata}

    # --- Live inference with key failover ----------------------------------
    # Provider demand spikes (e.g. Gemini 503 "high demand") can hit every
    # key at once but usually clear within seconds, so keys that failed with
    # a REAL provider error get up to two extra rounds with a short pause.
    # Simulated failures are never retried - they are deterministic for the
    # request - so the X-Simulate-Failure hook keeps its exact behaviour.
    simulate = parse_simulate_failure(x_simulate_failure) if settings.enable_failure_simulation else {}
    fallback_attempts = 0
    last_error: ProviderError | None = None
    simulated_failed: set[int] = set()
    real_failed: list[int] = []

    async def attempt(idx: int) -> tuple[str, int, int] | None:
        nonlocal fallback_attempts, last_error
        key_id = f"key_{idx + 1}"
        simulated_status = simulate.get(key_id, simulate.get("*"))
        if simulated_status is not None:
            fallback_attempts += 1
            simulated_failed.add(idx)
            last_error = ProviderError(simulated_status, f"simulated failure {simulated_status}")
            return None
        try:
            return await call_with_key(settings.llm_api_keys[idx], full_messages)
        except ProviderError as exc:
            # 429 / quota / 5xx -> fail over to the next key
            fallback_attempts += 1
            last_error = exc
            if idx not in real_failed:
                real_failed.append(idx)
            return None

    result: tuple[str, int, int] | None = None
    result_key_id: str | None = None

    for idx in range(len(settings.llm_api_keys)):
        outcome = await attempt(idx)
        if outcome is not None:
            result, result_key_id = outcome, f"key_{idx + 1}"
            break

    # Retry rounds for real failures only (demand-spike recovery).
    for pause in (6, 12):
        if result is not None:
            break
        retryable = [i for i in real_failed if i not in simulated_failed]
        if not retryable:
            break
        await asyncio.sleep(pause)
        real_failed = []
        for idx in retryable:
            outcome = await attempt(idx)
            if outcome is not None:
                result, result_key_id = outcome, f"key_{idx + 1}"
                break

    if result is not None:
        reply, input_tokens, output_tokens = result
        latency_ms = int((time.perf_counter() - start) * 1000)
        metadata = {
            "resolution_source": "LIVE_INFERENCE",
            "model": settings.llm_model,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "key_id": result_key_id,
            "fallback_attempts": fallback_attempts,
        }
        db.cache_put(cache_key, reply, settings.llm_model, input_tokens, output_tokens)
        db.add_message(payload.session_id, "user", payload.message)
        db.add_message(payload.session_id, "assistant", reply, metadata)
        return {"session_id": payload.session_id, "reply": reply, "metadata": metadata}

    # Every key failed: clean 503, nothing added to history
    raise HTTPException(status_code=503, detail="all providers unavailable")


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    db.init_db()
    if not db.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    messages = db.get_messages(session_id)
    if not messages and not db.session_exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "messages": messages}
