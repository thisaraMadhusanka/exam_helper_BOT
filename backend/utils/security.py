"""
Security utilities for signed anonymous workspace tokens.
Uses itsdangerous for cryptographically signed, expiring tokens.
"""
import secrets
import time
from typing import Optional
from uuid import UUID, uuid4

from itsdangerous import BadSignature, SignatureExpired, TimedSerializer

from utils.config import config


class TokenError(Exception):
    """Base exception for token errors."""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class TokenExpiredError(TokenError):
    """Token has expired."""
    def __init__(self, message: str = "Workspace token has expired"):
        super().__init__("TOKEN_EXPIRED", message)


class TokenInvalidError(TokenError):
    """Token signature is invalid or token is malformed."""
    def __init__(self, message: str = "Invalid workspace token"):
        super().__init__("TOKEN_INVALID", message)


class TokenMissingError(TokenError):
    """No token provided."""
    def __init__(self, message: str = "Authorization token required"):
        super().__init__("TOKEN_MISSING", message)


def _get_serializer() -> TimedSerializer:
    """Create a TimedSerializer with the session secret."""
    if not config.SESSION_SECRET:
        raise RuntimeError("SESSION_SECRET not configured")
    return TimedSerializer(config.SESSION_SECRET, salt="workspace-token")


def create_workspace_token() -> tuple[str, str, int]:
    """
    Create a new signed workspace token.

    Returns:
        tuple: (access_token, workspace_id, expires_in_seconds)
    """
    workspace_id = str(uuid4())
    expires_in = config.session_ttl_seconds

    serializer = _get_serializer()
    payload = {
        "workspace_id": workspace_id,
        "iat": int(time.time()),  # issued at
    }
    token = serializer.dumps(payload)

    return token, workspace_id, expires_in


def verify_workspace_token(token: str) -> str:
    """
    Verify a workspace token and return the workspace_id.

    Args:
        token: The signed token string

    Returns:
        The workspace_id (UUID string) from the token payload

    Raises:
        TokenMissingError: If token is empty/None
        TokenExpiredError: If token has expired
        TokenInvalidError: If token signature is invalid or malformed
    """
    if not token:
        raise TokenMissingError()

    serializer = _get_serializer()
    try:
        payload = serializer.loads(token, max_age=config.session_ttl_seconds)
    except SignatureExpired:
        raise TokenExpiredError()
    except BadSignature:
        raise TokenInvalidError()
    except Exception as e:
        # Catch any other deserialization errors
        raise TokenInvalidError(f"Token validation failed: {type(e).__name__}")

    workspace_id = payload.get("workspace_id")
    if not workspace_id:
        raise TokenInvalidError("Token missing workspace_id")

    # Validate it's a valid UUID format
    try:
        UUID(workspace_id)
    except ValueError:
        raise TokenInvalidError("Invalid workspace_id format in token")

    return workspace_id


def extract_token_from_header(auth_header: Optional[str]) -> str:
    """
    Extract bearer token from Authorization header.

    Args:
        auth_header: The Authorization header value

    Returns:
        The token string

    Raises:
        TokenMissingError: If header is missing or not Bearer
    """
    if not auth_header:
        raise TokenMissingError("Authorization header required")

    # Split only on first whitespace to handle tokens that may contain spaces
    parts = auth_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise TokenMissingError("Invalid Authorization header format. Expected: Bearer <token>")

    return parts[1]


def generate_secure_document_id() -> str:
    """Generate a cryptographically secure document ID."""
    return str(uuid4())