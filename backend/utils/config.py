"""
Centralized configuration for PDF RAG Assistant backend.
Loads settings from environment variables with sensible defaults.
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env file if present (local development)
_backend_env = Path(__file__).resolve().parent.parent / ".env"
if _backend_env.exists():
    load_dotenv(dotenv_path=_backend_env)
load_dotenv()



def _get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable with optional default."""
    return os.getenv(key, default)


def _get_env_int(key: str, default: int) -> int:
    """Get environment variable as integer with default."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_float(key: str, default: float) -> float:
    """Get environment variable as float with default."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


class Config:
    """Application configuration loaded from environment."""

    # Server port
    PORT: int = _get_env_int(
        "PORT",
        7860 if _get_env("SPACE_ID") else 8001,
    )

    # Admin credentials; authentication is disabled until a password is configured.
    ADMIN_EMAIL: str = _get_env("ADMIN_EMAIL", "") or ""
    ADMIN_USERNAME: str = _get_env("ADMIN_USERNAME", "admin") or "admin"
    ADMIN_PASSWORD: str = _get_env("ADMIN_PASSWORD", "") or ""
    ADMIN_ACCESS_CODE: str = _get_env("ADMIN_ACCESS_CODE", "ADMIN-TM-NEW") or "ADMIN-TM-NEW"

    # PDF processing settings
    CHUNK_SIZE: int = _get_env_int("CHUNK_SIZE", 500)
    CHUNK_OVERLAP: int = _get_env_int("CHUNK_OVERLAP", 50)
    MAX_UPLOAD_MB: int = _get_env_int("MAX_UPLOAD_MB", 20)
    MAX_PDF_PAGES: int = _get_env_int("MAX_PDF_PAGES", 200)

    # Session / workspace token settings
    SESSION_SECRET: str = _get_env("SESSION_SECRET", "")
    SESSION_TTL_HOURS: int = _get_env_int("SESSION_TTL_HOURS", 168)  # 7 days

    # CORS settings
    @property
    def CORS_ORIGINS(self) -> list[str]:
        raw = _get_env("CORS_ORIGINS")
        if raw is not None:
            return list(dict.fromkeys(o.strip() for o in raw.split(",") if o.strip()))

        return [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3002",
            "http://localhost:3003",
            "http://localhost:3004",
            "http://localhost:3005",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:3002",
            "http://127.0.0.1:3003",
            "http://127.0.0.1:3004",
            "http://127.0.0.1:3005",
        ]

    # Embedding settings (for Phase 2+)
    EMBEDDING_MODEL: str = _get_env("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    # Retrieval settings (for Phase 2+)
    TOP_K: int = _get_env_int("TOP_K", 4)
    MIN_SIMILARITY: Optional[float] = _get_env_float("MIN_SIMILARITY", 0.0)

    # LLM settings (for Phase 3)
    GROQ_API_KEY: Optional[str] = _get_env("GROQ_API_KEY")
    GROQ_MODEL: str = _get_env("GROQ_MODEL", "openai/gpt-oss-120b")
    GROQ_BASE_URL: str = _get_env("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

    OPENROUTER_API_KEY: Optional[str] = _get_env("OPENROUTER_API_KEY")
    OPENROUTER_MODEL: str = _get_env("OPENROUTER_MODEL", "openrouter/free")
    OPENROUTER_BASE_URL: str = _get_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    # Supabase settings (for Phase 2+)
    SUPABASE_URL: Optional[str] = _get_env("SUPABASE_URL")
    SUPABASE_KEY: Optional[str] = _get_env("SUPABASE_KEY")

    # Optional Hugging Face token for model downloads
    HF_TOKEN: Optional[str] = _get_env("HF_TOKEN")

    # Derived values
    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def session_ttl_seconds(self) -> int:
        return self.SESSION_TTL_HOURS * 3600


# Global config instance
config = Config()


def validate_required_config() -> list[str]:
    """
    Validate that required configuration is present.
    Returns list of missing required settings (empty if all present).
    """
    missing = []

    if not config.SESSION_SECRET:
        missing.append("SESSION_SECRET")
    if not config.ADMIN_EMAIL:
        missing.append("ADMIN_EMAIL (required for admin login)")
    if not config.ADMIN_PASSWORD:
        missing.append("ADMIN_PASSWORD (required for admin login)")

    # These are required for later phases but we warn early
    if not config.SUPABASE_URL:
        missing.append("SUPABASE_URL (required for Phase 2+)")
    if not config.SUPABASE_KEY:
        missing.append("SUPABASE_KEY (required for Phase 2+)")
    if not config.GROQ_API_KEY:
        missing.append("GROQ_API_KEY (required for Phase 3)")

    return missing
