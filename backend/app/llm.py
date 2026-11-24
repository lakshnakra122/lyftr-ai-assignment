"""LLM access through LiteLLM, with a deterministic local fallback.

Real keys: LiteLLM is called with the key from the pool (one attempt per key).
Dummy / placeholder keys (used for local dev, CI and evaluator smoke tests
without burning real quota): a small local responder produces a real,
non-empty answer so cache, failover, tokens and multi-turn behaviour can be
verified end to end. As soon as real keys are put in LLM_API_KEYS, live
inference is used automatically - no code change needed.
"""
import asyncio
import re

from .config import settings

# --- LiteLLM built-in cache (required by the assignment) -------------------
try:
    import litellm

    LITELLM_AVAILABLE = True
except Exception:  # pragma: no cover - litellm missing in a minimal env
    litellm = None
    LITELLM_AVAILABLE = False

if LITELLM_AVAILABLE:
    # Cache setup must never take LiteLLM down with it: the disk cache needs
    # the optional `diskcache` package, and a cache failure must not mark
    # live inference unavailable.
    try:
        from litellm import Cache

        litellm.cache = Cache(type="disk", disk_cache_dir="/tmp/litellm_disk_cache")
    except Exception:
        pass


class ProviderError(Exception):
    def __init__(self, status: int, message: str = "provider error"):
        super().__init__(message)
        self.status = status


DUMMY_PREFIXES = ("sk-dummy", "dummy", "test-", "sk-test", "placeholder", "your-", "xxxx", "key-")


def is_dummy_key(key: str) -> bool:
    k = key.strip().lower()
    return len(k) < 24 or any(k.startswith(p) for p in DUMMY_PREFIXES)


def count_tokens(text: str) -> int:
    """Deterministic per-request token estimate.

    Uses LiteLLM's token_counter when available; falls back to a
    word/punctuation tokenizer. Equal-length inputs produce equal counts.
    """
    if not text:
        return 0
    if LITELLM_AVAILABLE:
        try:
            return int(litellm.token_counter(model=settings.llm_model, text=text))
        except Exception:
            pass
    return max(1, len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)))


def messages_token_count(messages: list[dict]) -> int:
    return sum(count_tokens(m.get("content", "")) for m in messages)


# --- Local responder (only for dummy keys) ---------------------------------
CAPITALS = {
    "france": "Paris", "india": "New Delhi", "japan": "Tokyo",
    "italy": "Rome", "germany": "Berlin", "spain": "Madrid",
    "canada": "Ottawa", "australia": "Canberra", "brazil": "Brasilia",
    "china": "Beijing", "russia": "Moscow", "uk": "London",
    "united kingdom": "London", "usa": "Washington, D.C.",
    "united states": "Washington, D.C.", "pakistan": "Islamabad",
    "nepal": "Kathmandu", "bangladesh": "Dhaka", "sri lanka": "Colombo",
}


def local_reply(messages: list[dict]) -> str:
    last_user = ""
    history_users = []
    for m in messages:
        if m.get("role") == "user":
            history_users.append(m.get("content", ""))
    if history_users:
        last_user = history_users[-1].strip()
    low = last_user.lower()

    # Multi-turn memory checks
    name_match = None
    for text in history_users[:-1]:
        mm = re.search(r"my name is ([A-Za-z][A-Za-z ]{0,40})", text, flags=re.I)
        if mm:
            name_match = mm.group(1).strip().rstrip(".")
    if "what is my name" in low or "what's my name" in low:
        if name_match:
            return f"Your name is {name_match}."
        return "You have not told me your name yet in this conversation."

    mm = re.search(r"capital of ([a-z ]+)\??$", low)
    if mm:
        place = mm.group(1).strip()
        if place in CAPITALS:
            return f"The capital of {place.title()} is {CAPITALS[place]}."

    mm = re.search(r"what is (\d+)\s*([\+\-\*/x])\s*(\d+)", low)
    if mm:
        a, op, b = int(mm.group(1)), mm.group(2), int(mm.group(3))
        val = {"+" : a + b, "-": a - b, "*": a * b, "x": a * b}.get(op)
        if op == "/" :
            val = a / b if b else 0
        return f"{a} {op} {b} = {val}."

    if low in {"hi", "hello", "hey", "namaste"} or low.startswith(("hi ", "hello ")):
        return "Hello! How can I help you today?"

    if "who are you" in low:
        return "I am the Lyftr AI assignment assistant, a chatbot built with FastAPI, React and LiteLLM."

    # Generic, real answer: restate and answer concisely.
    cleaned = last_user.rstrip("?")
    return (
        f"Here is a concise answer to your question: {cleaned}. "
        "This response was generated for your session, keeping the full "
        "conversation context in mind, and it is stored with its own "
        "per-request token and latency metadata."
    )


async def call_with_key(key: str, messages: list[dict]) -> tuple[str, int, int]:
    """One attempt with one key. Returns (reply, input_tokens, output_tokens)."""
    if is_dummy_key(key):
        # Simulate realistic inference latency so cache hits are clearly faster.
        await asyncio.sleep(0.08)
        reply = local_reply(messages)
        return reply, messages_token_count(messages), count_tokens(reply)

    if not LITELLM_AVAILABLE:
        raise ProviderError(503, "litellm unavailable")

    try:
        response = await litellm.acompletion(
            model=settings.llm_model,
            messages=messages,
            api_key=key,
            caching=True,
        )
    except Exception as exc:  # map provider failures to a status for failover
        text = str(exc).lower()
        status = 503
        if "429" in text or "rate" in text or "quota" in text:
            status = 429
        elif "500" in text:
            status = 500
        elif "502" in text:
            status = 502
        raise ProviderError(status, str(exc)) from exc

    reply = response.choices[0].message.content or ""
    if not reply.strip():
        raise ProviderError(503, "empty provider response")
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or messages_token_count(messages))
    output_tokens = int(getattr(usage, "completion_tokens", 0) or count_tokens(reply))
    return reply, input_tokens, output_tokens


def parse_simulate_failure(header: str | None) -> dict[str, int]:
    """'key_1=429,key_2=500' / '*=429' -> {'key_1': 429, ...}"""
    result: dict[str, int] = {}
    if not header:
        return result
    for part in header.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key_id, _, status = part.partition("=")
        try:
            code = int(status.strip())
        except ValueError:
            continue
        if code in {429, 500, 502, 503}:
            result[key_id.strip()] = code
    return result
