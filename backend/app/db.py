import json
import os
import sqlite3
from datetime import datetime, timezone

from .config import settings


def db_path_from_url(url: str) -> str:
    # sqlite:////data/app.db -> /data/app.db ; sqlite:///./app.db -> ./app.db
    if url.startswith("sqlite:////"):
        return "/" + url[len("sqlite:////"):]
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    if url.startswith("sqlite://"):
        return url[len("sqlite://"):]
    return url


DB_PATH = db_path_from_url(settings.database_url)


def get_conn() -> sqlite3.Connection:
    directory = os.path.dirname(os.path.abspath(DB_PATH))
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                system_prompt TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key TEXT PRIMARY KEY,
                reply TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def ensure_session(session_id: str, system_prompt: str | None) -> None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO sessions (session_id, system_prompt, created_at) VALUES (?, ?, ?)",
                (session_id, system_prompt, now_iso()),
            )
        elif system_prompt:
            conn.execute(
                "UPDATE sessions SET system_prompt = ? WHERE session_id = ?",
                (system_prompt, session_id),
            )
        conn.commit()
    finally:
        conn.close()


def get_system_prompt(session_id: str) -> str | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return row["system_prompt"] if row else None
    finally:
        conn.close()


def session_exists(session_id: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return row is not None
    finally:
        conn.close()


def add_message(session_id: str, role: str, content: str, metadata: dict | None = None) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, json.dumps(metadata) if metadata else None, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def get_messages(session_id: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        result = []
        for r in rows:
            item = {"role": r["role"], "content": r["content"]}
            if r["role"] == "assistant" and r["metadata"]:
                try:
                    item["metadata"] = json.loads(r["metadata"])
                except json.JSONDecodeError:
                    pass
            result.append(item)
        return result
    finally:
        conn.close()


def cache_get(cache_key: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM llm_cache WHERE cache_key = ?", (cache_key,)).fetchone()
        if row is None:
            return None
        return {
            "reply": row["reply"],
            "model": row["model"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
        }
    finally:
        conn.close()


def cache_put(cache_key: str, reply: str, model: str, input_tokens: int, output_tokens: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache (cache_key, reply, model, input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cache_key, reply, model, input_tokens, output_tokens, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
