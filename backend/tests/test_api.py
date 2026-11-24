import os
import sys
import tempfile

# Isolated DB + dummy keys + failure simulation BEFORE importing the app
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["LLM_API_KEYS"] = "sk-dummy-key-1,sk-dummy-key-2"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["keys_configured"] == 2
    assert body["cache_enabled"] is True


def test_chat_live_then_cache_in_new_session():
    r1 = client.post("/chat", json={"session_id": "s-test-1", "message": "What is the capital of France?"})
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["reply"] == "The capital of France is Paris."
    assert b1["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert b1["metadata"]["key_id"] == "key_1"
    assert b1["metadata"]["fallback_attempts"] == 0
    assert isinstance(b1["metadata"]["latency_ms"], int)
    assert b1["metadata"]["input_tokens"] > 0
    assert b1["metadata"]["output_tokens"] > 0

    # Same first message in a NEW session -> cache hit, identical reply
    r2 = client.post("/chat", json={"session_id": "s-test-2", "message": "What is the capital of France?"})
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["metadata"]["resolution_source"] == "LLM_CACHE"
    assert b2["reply"] == b1["reply"]
    assert b2["metadata"]["key_id"] is None
    assert b2["metadata"]["fallback_attempts"] == 0
    assert b2["metadata"]["input_tokens"] == b1["metadata"]["input_tokens"]
    assert b2["metadata"]["latency_ms"] <= b1["metadata"]["latency_ms"]


def test_different_message_not_cached():
    r = client.post("/chat", json={"session_id": "s-test-3", "message": "What is the capital of Japan?"})
    assert r.status_code == 200
    assert r.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert r.json()["reply"] == "The capital of Japan is Tokyo."


def test_failover_key1_429():
    r = client.post(
        "/chat",
        json={"session_id": "s-fail-1", "message": "What is the capital of Italy?"},
        headers={"X-Simulate-Failure": "key_1=429"},
    )
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_2"
    assert r.json()["metadata"]["fallback_attempts"] == 1


def test_failover_key1_500():
    r = client.post(
        "/chat",
        json={"session_id": "s-fail-2", "message": "What is the capital of Spain?"},
        headers={"X-Simulate-Failure": "key_1=500"},
    )
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_2"


def test_all_keys_fail_503_and_not_in_history():
    r = client.post(
        "/chat",
        json={"session_id": "s-fail-all", "message": "What is the capital of Canada?"},
        headers={"X-Simulate-Failure": "*=429"},
    )
    assert r.status_code == 503
    assert r.json() == {"detail": "all providers unavailable"}
    hist = client.get("/sessions/s-fail-all/messages")
    # Session row may exist but no messages must have been stored for the failed request
    if hist.status_code == 200:
        assert hist.json()["messages"] == []


def test_validation_422():
    assert client.post("/chat", json={"session_id": "s-x", "message": ""}).status_code == 422
    assert client.post("/chat", json={"session_id": "s-x", "message": "   "}).status_code == 422
    assert client.post("/chat", json={"session_id": "", "message": "hi"}).status_code == 422
    assert client.post("/chat", json={"session_id": "s-x", "message": "x" * 4001}).status_code == 422
    assert client.post("/chat", json={"message": "hi"}).status_code == 422


def test_unknown_session_404():
    r = client.get("/sessions/does-not-exist-123/messages")
    assert r.status_code == 404
    assert r.json() == {"detail": "session not found"}


def test_multi_turn_and_history():
    client.post("/chat", json={"session_id": "s-multi", "message": "Hi, my name is Laksh."})
    r = client.post("/chat", json={"session_id": "s-multi", "message": "What is my name?"})
    assert r.status_code == 200
    assert "Laksh" in r.json()["reply"]
    hist = client.get("/sessions/s-multi/messages")
    assert hist.status_code == 200
    msgs = hist.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[1]["metadata"]["resolution_source"] in {"LIVE_INFERENCE", "LLM_CACHE"}


def test_per_request_tokens_not_total():
    a = client.post("/chat", json={"session_id": "s-tok-1", "message": "Hello there friend"})
    b = client.post("/chat", json={"session_id": "s-tok-2", "message": "Hello there friend"})
    # Equal-length first messages in two sessions -> about the same input tokens (here: cache, identical)
    assert a.json()["metadata"]["input_tokens"] == b.json()["metadata"]["input_tokens"]
