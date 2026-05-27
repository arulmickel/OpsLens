"""Dashboard login. Bcrypt hash compare, rate-limited."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import bcrypt

from src.config import get_settings
from src.security.rate_limiter import LOGIN_LIMITER
from src.security.validation import LoginRequest


@dataclass
class AuthResult:
    success: bool
    message: str
    retry_after_seconds: int = 0


def hash_password(password: str) -> str:
    """Utility for generating a bcrypt hash for the env file."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def authenticate(username: str, password: str) -> AuthResult:
    settings = get_settings()
    try:
        req = LoginRequest(username=username, password=password)
    except Exception as e:
        return AuthResult(success=False, message=f"Invalid input: {e}")

    key = req.username.lower()
    pre = LOGIN_LIMITER.check(key)
    if not pre.allowed:
        return AuthResult(
            success=False,
            message=(
                f"Too many failed attempts. Try again in "
                f"{pre.retry_after_seconds} seconds."
            ),
            retry_after_seconds=pre.retry_after_seconds,
        )

    expected_user = settings.dashboard_username
    stored_hash = settings.dashboard_password_hash

    if not stored_hash or not stored_hash.startswith("$2"):
        return AuthResult(
            success=False,
            message=(
                "Dashboard password is not configured. "
                "Generate a bcrypt hash and set DASHBOARD_PASSWORD_HASH."
            ),
        )

    if req.username != expected_user or not _safe_verify(req.password, stored_hash):
        recorded = LOGIN_LIMITER.record(key)
        if not recorded.allowed:
            return AuthResult(
                success=False,
                message=(
                    f"Account locked. Try again in "
                    f"{recorded.retry_after_seconds} seconds."
                ),
                retry_after_seconds=recorded.retry_after_seconds,
            )
        return AuthResult(
            success=False,
            message=(
                f"Invalid credentials. {recorded.remaining} attempt(s) remaining "
                "before lockout."
            ),
        )

    LOGIN_LIMITER.reset(key)
    return AuthResult(success=True, message="Authenticated")


def _safe_verify(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False
