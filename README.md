# Lyftr AI — LLM Chatbot with Key Failover and Response Caching

Full-stack assignment: React frontend + FastAPI backend + SQLite, using LiteLLM
for multi-key failover and response caching, with per-request token tracking.

## 1. Live URLs

- **Frontend:** _Add your Vercel/Netlify URL here after deployment (see Deployment notes below)_
- **Backend:** _Add your Render/Railway URL here after deployment_
- **Backend health check:** `<backend-url>/health`

> Deployment is a 10-minute step with your own accounts (instructions at the
> bottom of this README). Everything else — code, Docker, tests, contract —
> is complete and verified locally. No real API keys are stored in this repo.

## 2. Run locally

### With Docker (recommended, matches the assignment)

```bash
cp .env.example .env   # fill in LLM_API_KEYS (at least 2 keys)
make up                # backend http://localhost:8000 , frontend http://localhost:3000
make down              # stop
```

### Without Docker

Backend:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
LLM_API_KEYS=sk-dummy-key-1,sk-dummy-key-2 DATABASE_URL=sqlite:///./app.db \
ENABLE_FAILURE_SIMULATION=true uvicorn app.main:app --port 8000
```

Frontend (new terminal):
```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

Tests:
```bash
make test   # or: cd backend && python -m pytest -q   (10 tests)
```

**No real keys handy?** Use the dummy keys shown above. The app then runs in
local-responder mode: it returns real, non-empty answers (capitals, simple
maths, name memory, generic concise answers) so cache, failover, tokens and
multi-turn can all be verified. Put real keys in `LLM_API_KEYS` and the same
code automatically switches to live LiteLLM inference — no code change.

## 3. Design decisions

### Key fallback
- Keys come from `LLM_API_KEYS` (comma-separated); ids are `key_1`, `key_2`, …
  in that order. The secret value is never returned — only the id.
- `POST /chat` tries keys in order. A 429, quota error or 5xx from a key
  increments `fallback_attempts` and moves to the next key automatically.
- If every key fails, the API returns `503 {"detail": "all providers unavailable"}`
  and **nothing is written to history** for that request.
- `X-Simulate-Failure: key_1=429` (or `*=429`, statuses 429/500/502/503) makes
  chosen keys fail for that one request only, and is honoured only when
  `ENABLE_FAILURE_SIMULATION=true`.

### Caching
- LiteLLM's built-in cache is enabled (`litellm.cache = Cache(type="disk")`,
  `caching=True` on completions).
- On top of it, an explicit application cache in SQLite (`llm_cache` table)
  makes the contract deterministic and auditable: the cache key is
  SHA-256 of `model + full message list (system + history + new message)`.
- A hit returns the **identical** reply, the stored per-request tokens,
  `resolution_source: "LLM_CACHE"`, `key_id: null`, `fallback_attempts: 0`,
  and a much lower `latency_ms`. A different message can never hit another
  message's entry, and the same first message in a new session is a hit.

### SQLite session storage
- SQLite only — no Redis, no Postgres. Path comes from `DATABASE_URL`
  (`sqlite:////data/app.db` in Docker, on the named `app_data` volume, so
  history survives container restarts). Schema is created on startup.
- Tables: `messages` (exactly the assignment's model, plus an index),
  `sessions` (stores the per-session system prompt), `llm_cache`.
- The client sends only the new message; the backend rebuilds
  system + history + new message from SQLite for every request, so the bot
  remembers earlier turns and sessions stay fully separate.
- Tokens and latency are stored **per assistant message** in its `metadata`
  JSON — never as a running total.

### API contract
Exactly three endpoints: `GET /health`, `POST /chat`,
`GET /sessions/{session_id}/messages`, with the exact field names from the
assignment. Validation errors are FastAPI 422 JSON, unknown sessions are
`404 {"detail": "session not found"}`, and no stack trace or HTML error
page is ever returned.

## 4. Verification

Health:
```bash
curl http://localhost:8000/health
# {"status":"ok","keys_configured":2,"cache_enabled":true}
```

Live call, then cache hit (same first message, new session):
```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"s-1","message":"What is the capital of France?"}'
# LIVE_INFERENCE, key_1, latency ~80ms+ (or ~800ms with a real provider)

curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"s-2","message":"What is the capital of France?"}'
# LLM_CACHE, identical reply, key_id null, much lower latency
```

Failover:
```bash
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: key_1=429' \
  -d '{"session_id":"s-3","message":"What is the capital of Japan?"}'
# 200, key_id = key_2, fallback_attempts = 1

curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: *=429' \
  -d '{"session_id":"s-4","message":"Hello"}'
# 503 {"detail":"all providers unavailable"}
```

History & tokens: `curl http://localhost:8000/sessions/s-1/messages` — every
assistant message carries its own metadata; in the UI the same metadata is
shown next to each reply (`meta-source`, `meta-model`, `meta-latency`,
`meta-input-tokens`, `meta-output-tokens`).

## 5. Setup Used

- Editor: VS Code-style workflow with Muse (AI assistant) for scaffolding,
  implementation and test verification; Python 3.12, Node 20.
- AI tools: Muse for code generation and review; LiteLLM documentation for
  the cache and multi-key configuration.
- All backend behaviour is covered by the pytest suite in `backend/tests/`.

## 6. Bonus features (if any)

- **Local-responder mode for dummy keys** — the whole contract (cache,
  failover, tokens, multi-turn memory such as “What is my name?”) can be
  demoed and tested with zero real API quota, then switches to live
  inference automatically when real keys are configured.
- **System prompt per session** in the UI (`system-prompt-input`), stored in
  SQLite and applied to every turn of that session.
- **Render blueprint** (`render.yaml`) for one-click backend deployment.
- Readable in-chat error handling for 422/503 — never a blank screen.

---

## Deployment notes (for the submitter)

1. **Backend — Render/Railway/Fly.io:** create a Docker web service from
   `backend/` (or use `render.yaml`), add a persistent disk mounted at `/data`,
   and set env vars: `LLM_API_KEYS` (2+ real keys), `LLM_MODEL`,
   `DATABASE_URL=sqlite:////data/app.db`, `ENABLE_FAILURE_SIMULATION=true`,
   `ALLOWED_ORIGINS=<your frontend URL>`.
2. **Frontend — Vercel/Netlify:** import `frontend/`, set build command
   `npm run build`, output `dist`, and env `VITE_API_URL=<your backend URL>`.
3. Put both live URLs in section 1 above, push to a public GitHub repo, and
   record the 2–3 minute demo (health → live chat → same message in a new
   session = cache hit → failover with `X-Simulate-Failure` via curl/Postman
   → history endpoint).
