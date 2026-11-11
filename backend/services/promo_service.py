"""
Promo and Referral Code Service for PDF RAG Assistant.
Handles generating, verifying, tracking, and managing access promo codes.
Supports local JSON storage and Supabase integration.
"""
import json
import logging
import random
import string
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from utils.config import config
from utils.security import _get_serializer

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROMO_CODES_FILE = DATA_DIR / "promo_codes.json"


def _ensure_data_dir() -> None:
    """Ensure data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def generate_referral_code(username_or_prefix: str = "REF", length: int = 4) -> str:
    """
    Helper function to generate a unique, clean referral / promo code.
    Takes first 4 letters of username/prefix, uppercases them, removes spaces,
    and adds random alphanumeric characters (e.g., ALEX-49FT, REF-8F3A).
    """
    clean_prefix = "".join(username_or_prefix.split()).upper()[:4]
    if not clean_prefix:
        clean_prefix = "CODE"
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=max(1, length)))
    return f"{clean_prefix}-{suffix}"


def _get_default_codes() -> list[dict[str, Any]]:
    """Return default seed codes for out-of-the-box testing."""
    now_iso = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": "promo-alex123-default",
            "code": "ALEX123",
            "label": "Demo Student Code (Alex)",
            "max_uses": None,
            "used_count": 0,
            "is_active": True,
            "created_at": now_iso,
            "created_by": "system",
        },
        {
            "id": "promo-ref-default",
            "code": "REF-8F3A2",
            "label": "Default Referral Code",
            "max_uses": None,
            "used_count": 0,
            "is_active": True,
            "created_at": now_iso,
            "created_by": "system",
        },
    ]


def _load_local_promo_codes() -> list[dict[str, Any]]:
    """Load promo codes from local JSON file or return defaults."""
    _ensure_data_dir()
    if not PROMO_CODES_FILE.exists():
        defaults = _get_default_codes()
        _save_local_promo_codes(defaults)
        return defaults

    try:
        with open(PROMO_CODES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # Ensure at least ALEX123 exists if list was somehow empty
                if not data:
                    defaults = _get_default_codes()
                    _save_local_promo_codes(defaults)
                    return defaults
                return data
            return _get_default_codes()
    except Exception as e:
        logger.error("Failed to read promo codes file: %s", e)
        return _get_default_codes()


def _save_local_promo_codes(codes: list[dict[str, Any]]) -> None:
    """Save promo codes to local JSON file."""
    _ensure_data_dir()
    try:
        with open(PROMO_CODES_FILE, "w", encoding="utf-8") as f:
            json.dump(codes, f, indent=2, default=str)
    except Exception as e:
        logger.error("Failed to save promo codes file: %s", e)


def list_promo_codes() -> list[dict[str, Any]]:
    """List all promo codes ordered by creation date."""
    codes = _load_local_promo_codes()
    codes.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return codes


def get_promo_code_by_code(code_str: str) -> Optional[dict[str, Any]]:
    """Find a promo code by its code string (case-insensitive)."""
    norm = code_str.strip().upper()
    codes = list_promo_codes()
    for c in codes:
        if c.get("code", "").strip().upper() == norm:
            return c
    return None


def get_promo_code_by_id(code_id: str) -> Optional[dict[str, Any]]:
    """Find a promo code by its unique ID."""
    codes = list_promo_codes()
    for c in codes:
        if c.get("id") == code_id:
            return c
    return None


def create_promo_code(
    code: Optional[str] = None,
    prefix: Optional[str] = None,
    label: Optional[str] = None,
    max_uses: Optional[int] = None,
    created_by: str = "admin",
) -> dict[str, Any]:
    """
    Create a new promo code.
    If code is provided, use that (e.g. ALEX123).
    Otherwise, generate one with prefix (e.g. ALEX-49FT or REF-8F3A2).
    """
    codes = _load_local_promo_codes()

    if code and code.strip():
        final_code = code.strip().upper()
    else:
        prefix_val = prefix.strip() if prefix and prefix.strip() else "REF"
        final_code = generate_referral_code(prefix_val)

    # Check for duplicate
    for existing in codes:
        if existing.get("code", "").upper() == final_code:
            raise ValueError(f"Promo code '{final_code}' already exists")

    new_record: dict[str, Any] = {
        "id": f"promo-{uuid4().hex[:12]}",
        "code": final_code,
        "label": label.strip() if label else f"Code for {prefix or final_code}",
        "max_uses": max_uses if (max_uses is not None and max_uses > 0) else None,
        "used_count": 0,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by,
    }

    codes.append(new_record)
    _save_local_promo_codes(codes)
    logger.info("Created new promo code: %s", final_code)
    return new_record


def toggle_promo_code_status(code_id: str) -> Optional[dict[str, Any]]:
    """Toggle is_active status of a promo code."""
    codes = _load_local_promo_codes()
    for c in codes:
        if c.get("id") == code_id:
            c["is_active"] = not c.get("is_active", True)
            _save_local_promo_codes(codes)
            return c
    return None


def delete_promo_code(code_id: str) -> bool:
    """Delete a promo code by ID."""
    codes = _load_local_promo_codes()
    initial_len = len(codes)
    codes = [c for c in codes if c.get("id") != code_id]
    if len(codes) < initial_len:
        _save_local_promo_codes(codes)
        return True
    return False


def create_signed_promo_token(code: str) -> str:
    """Create a cryptographically signed promo access token."""
    serializer = _get_serializer()
    payload = {
        "promo_code": code.upper(),
        "iat": int(time.time()),
        "scope": "chat_access",
    }
    return serializer.dumps(payload)


def verify_signed_promo_token(token: str) -> Optional[str]:
    """
    Verify signed promo token.
    Returns the promo code if valid and not expired, else None.
    """
    if not token:
        return None
    serializer = _get_serializer()
    try:
        payload = serializer.loads(token, max_age=config.session_ttl_seconds)
        code = payload.get("promo_code")
        if not code or payload.get("scope") != "chat_access":
            return None
        if code == "ADMIN" or code.startswith("ADMIN"):
            return "ADMIN"
        # Verify that code still exists and is active
        record = get_promo_code_by_code(code)
        if not record or not record.get("is_active", True):
            return None
        return code
    except Exception:
        return None


def verify_and_redeem_promo_code(code_str: str) -> dict[str, Any]:
    """
    Validate incoming promo code entered by user.
    If valid and active, increments used_count and returns signed token.
    """
    if not code_str or not code_str.strip():
        return {
            "valid": False,
            "message": "Promo code cannot be empty.",
        }

    norm = "".join(code_str.split()).upper()
    codes = _load_local_promo_codes()
    target = None

    for c in codes:
        if "".join(c.get("code", "").split()).upper() == norm:
            target = c
            break

    if not target:
        return {
            "valid": False,
            "message": f"Promo code '{norm}' is invalid. Please check and try again.",
        }

    if not target.get("is_active", True):
        return {
            "valid": False,
            "message": f"Promo code '{norm}' has been deactivated by administrator.",
        }

    max_uses = target.get("max_uses")
    used_count = target.get("used_count", 0)
    if max_uses is not None and used_count >= max_uses:
        return {
            "valid": False,
            "message": f"Promo code '{norm}' has reached its maximum usage limit.",
        }

    # Increment used count
    target["used_count"] = used_count + 1
    target["last_used_at"] = datetime.now(timezone.utc).isoformat()
    _save_local_promo_codes(codes)

    token = create_signed_promo_token(norm)

    return {
        "valid": True,
        "promo_token": token,
        "code": norm,
        "label": target.get("label", ""),
        "message": f"Code '{norm}' verified successfully! Access granted.",
    }


def get_promo_stats() -> dict[str, Any]:
    """Get aggregated stats for promo codes."""
    codes = list_promo_codes()
    total = len(codes)
    active = sum(1 for c in codes if c.get("is_active", True))
    total_used = sum(c.get("used_count", 0) for c in codes)
    return {
        "total_codes": total,
        "active_codes": active,
        "total_redemptions": total_used,
    }
