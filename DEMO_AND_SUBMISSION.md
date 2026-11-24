# Demo Video Script (2–3 minutes) + Submission Checklist

## Before recording
- Deploy backend + frontend (README → Deployment notes), put real keys in the
  backend env, and paste both live URLs into README section 1.
- Keep a terminal / Postman ready for the failover call.

## Script (say this while showing the screen)

**0:00–0:25 — Intro + health**
"This is my Lyftr AI assignment — a multi-turn LLM chatbot built with React,
FastAPI, SQLite and LiteLLM. First, the health endpoint: status ok, two keys
configured, cache enabled." (Show `GET /health` in the browser.)

**0:25–1:00 — Live chat + metadata**
"In the UI I ask: What is the capital of France? The reply is Paris, and next
to it you can see the metadata for this request only — LIVE_INFERENCE, the
model name, latency in milliseconds, and input and output tokens. I also set
an optional system prompt at the top, and the bot remembers context — I tell
it my name, then ask 'What is my name?' and it answers correctly."

**1:00–1:35 — Cache hit**
"Now I reload the page — that starts a new session — and send the exact same
first message. This time the source is LLM_CACHE, the reply is identical,
key_id is null, tokens are the same, and latency drops from about 80
milliseconds to just a few milliseconds."

**1:35–2:20 — Failover**
"For failover I use the test hook. In Postman I send a chat request with the
header X-Simulate-Failure: key_1=429. The response is still 200, but key_id is
now key_2 and fallback_attempts is 1 — the user never sees an error. If I set
the header to *=429, every key fails and the API returns a clean 503 —
'all providers unavailable' — and that failed request is not added to history,
which I can show with the history endpoint."

**2:20–2:50 — History + wrap-up**
"The history endpoint returns the full session from SQLite, oldest first,
each assistant message with its own metadata. Locally the whole stack starts
with one command — make up — backend on 8000, frontend on 3000, with the
database on a Docker volume. Thank you."

## Submission checklist
- [ ] Backend deployed, `/health` opens publicly
- [ ] Frontend deployed, chat works against the deployed backend
- [ ] `ENABLE_FAILURE_SIMULATION=true` set on the deployed backend
- [ ] README section 1 filled with both live URLs
- [ ] Code pushed to a **public** GitHub repo (no real keys — `.env` is gitignored)
- [ ] Demo video recorded (script above) and uploaded
- [ ] Submission form submitted within 24 hours of receiving the assignment
- [ ] Internship note: role is 6 months, full-time, **on-site in Sector 48,
      Gurugram**, stipend ₹30,000/month (up to ₹45,000), PPO ₹9 LPA.
      Application email: careers@lyftr.ai — Subject: "Full Stack Developer
      Intern Application" (resume + GitHub profile)
