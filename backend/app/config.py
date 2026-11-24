import os


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        raw_keys = os.getenv("LLM_API_KEYS", "sk-dummy-key-1,sk-dummy-key-2")
        self.llm_api_keys: list[str] = [k.strip() for k in raw_keys.split(",") if k.strip()]
        self.llm_model: str = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
        raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
        self.allowed_origins: list[str] = [o.strip() for o in raw_origins.split(",") if o.strip()] or ["*"]
        self.enable_failure_simulation: bool = _bool(os.getenv("ENABLE_FAILURE_SIMULATION", "true"))
        self.cache_enabled: bool = True
        self.default_system_prompt: str = os.getenv(
            "DEFAULT_SYSTEM_PROMPT",
            "You are a helpful, concise assistant. Answer clearly in a few sentences.",
        )

    @property
    def key_ids(self) -> list[str]:
        return [f"key_{i + 1}" for i in range(len(self.llm_api_keys))]


settings = Settings()
