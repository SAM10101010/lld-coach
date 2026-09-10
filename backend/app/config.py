"""Central configuration. Reads from environment with safe defaults for demo."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


DATABASE_URL: str = _get("DATABASE_URL", "sqlite:///./lldcoach.db")
OPENAI_API_KEY: str = _get("OPENAI_API_KEY", "")
# OpenRouter (OpenAI-compatible). When set, it is preferred in "auto" mode.
OPENROUTER_API_KEY: str = _get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = _get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
# auto | openai | openrouter | heuristic
AI_PROVIDER: str = (_get("AI_PROVIDER", "auto") or "auto").lower()
AI_MODEL: str = _get("AI_MODEL", "gpt-4o-mini")
AI_TIMEOUT_SECONDS: int = int(_get("AI_TIMEOUT_SECONDS", "30") or 30)
CORS_ORIGINS: str = _get("CORS_ORIGINS", "*")
