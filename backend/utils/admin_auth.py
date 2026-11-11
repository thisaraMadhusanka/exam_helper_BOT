"""
Admin authentication utilities for PDF RAG Assistant.
Provides password verification and signed Admin tokens.
"""
import secrets
import time
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, TimedSerializer

from utils.config import config
from utils.security import TokenError, TokenExpiredError, TokenInvalidError, TokenMissingError


def _get_admin_serializer() -> TimedSerializer:
    """Create a TimedSerializer for admin tokens."""
    if not config.SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET not configured")
    return TimedSerializer(config.SESSION_SECRET, salt="admin-token")


def verify_admin_credentials(email: str, password: str) -> bool:
    """Check configured admin email and password using constant-time comparisons."""
    expected_email = config.ADMIN_EMAIL.strip().casefold()
    expected_password = config.ADMIN_PASSWORD
    if not email or not password or not expected_email or not expected_password:
        return False
    email_matches = secrets.compare_digest(
        email.strip().casefold().encode("utf-8"),
        expected_email.encode("utf-8"),
    )
    password_matches = secrets.compare_digest(
        password.encode("utf-8"),
        expected_password.encode("utf-8"),
    )
    return email_matches and password_matches


def verify_admin_code(code: str) -> bool:
    """Check configured single admin access code using constant-time comparison, ignoring spaces."""
    if not code or not str(code).strip():
        return False
    norm_code = "".join(str(code).split()).upper()
    expected_code = "".join(config.ADMIN_ACCESS_CODE.split()).upper()
    if not expected_code:
        return False
    return secrets.compare_digest(
        norm_code.encode("utf-8"),
        expected_code.encode("utf-8"),
    )


def create_admin_token(expires_in_hours: int = 24) -> tuple[str, int]:
    """
    Create a new signed admin token.

    Returns:
        tuple: (access_token, expires_in_seconds)
    """
    expires_in_seconds = expires_in_hours * 3600
    serializer = _get_admin_serializer()
    payload = {
        "role": "admin",
        "iat": int(time.time()),
    }
    token = serializer.dumps(payload)
    return token, expires_in_seconds


def verify_admin_token(token: str, max_age_seconds: int = 86400) -> bool:
    """
    Verify that an admin token is valid and unexpired.

    Raises:
        TokenMissingError, TokenExpiredError, TokenInvalidError
    """
    if not token or not token.strip():
        raise TokenMissingError("Admin authorization token is required")

    serializer = _get_admin_serializer()
    try:
        payload = serializer.loads(token, max_age=max_age_seconds)
    except SignatureExpired:
        raise TokenExpiredError("Admin session has expired. Please log in again.")
    except (BadSignature, Exception) as e:
        raise TokenInvalidError("Invalid admin session token")

    if not isinstance(payload, dict) or payload.get("role") != "admin":
        raise TokenInvalidError("Token does not have admin permissions")

    return True
