"""Password hashing, JWT helpers, and lightweight auth rate limiting."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque

from fastapi import HTTPException, Request, status
from jose import jwt
from jose.exceptions import JWTError
from passlib.context import CryptContext

from app.core.config import settings


# Standard bcrypt keeps compatibility with the Phase 1 password column. For
# unusually long passwords, deterministically pre-hash to a 44-byte value so
# bcrypt never silently truncates user input.
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _bcrypt_input(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) <= 72:
        return password

    digest = hashlib.sha256(encoded).digest()
    return base64.b64encode(digest).decode("ascii")


def hash_password(password: str) -> str:
    bcrypt_input = _bcrypt_input(password)
    return password_context.hash(bcrypt_input)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        bcrypt_input = _bcrypt_input(password)
        return password_context.verify(bcrypt_input, hashed_password)
    except (TypeError, ValueError):
        return False


def _expiry_for(kind: str) -> datetime:
    if kind == "access":
        return datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def create_token(user_id: str, kind: str) -> str:
    """Create a signed, typed JWT for an account."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": kind,
        "iat": now,
        "exp": _expiry_for(kind),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_token_pair(user_id: str) -> tuple[str, str]:
    return create_token(user_id, "access"), create_token(user_id, "refresh")


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    """Decode and validate a Catalyst JWT.

    Raises ``JWTError`` for expired, malformed, wrongly signed, or
    wrongly typed tokens so route handlers can turn it into a consistent 401.
    """
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    subject = payload.get("sub")
    if not subject or not isinstance(subject, str):
        raise JWTError("Token subject is missing")
    token_type = payload.get("type")
    if token_type not in {"access", "refresh"}:
        raise JWTError("Token type is invalid")
    if expected_type is not None and token_type != expected_type:
        raise JWTError("Token type does not match this endpoint")
    return payload


# The limiter tracks authentication requests per client and endpoint. It is
# process-local and suitable for the current single-process deployment; a
# shared store can replace it later if the API is scaled horizontally.
_auth_failures: dict[tuple[str, str], Deque[float]] = defaultdict(deque)
_auth_lock = asyncio.Lock()


def _client_key(request: Request) -> str:
    # Do not trust X-Forwarded-For unless a trusted proxy is explicitly
    # configured; otherwise a caller could bypass the per-IP limiter.
    return request.client.host if request.client else "unknown"


def _failure_key(request: Request) -> tuple[str, str]:
    return _client_key(request), request.url.path


async def ensure_auth_attempt_allowed(request: Request) -> None:
    """Raise 429 after the configured number of auth requests per IP."""
    if settings.AUTH_RATE_LIMIT <= 0:
        return
    key = _failure_key(request)
    now = time.monotonic()
    async with _auth_lock:
        attempts = _auth_failures[key]
        cutoff = now - settings.AUTH_RATE_WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= settings.AUTH_RATE_LIMIT:
            retry_after = max(1, int(settings.AUTH_RATE_WINDOW_SECONDS - (now - attempts[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )


async def record_auth_attempt(request: Request) -> None:
    if settings.AUTH_RATE_LIMIT <= 0:
        return
    key = _failure_key(request)
    now = time.monotonic()
    async with _auth_lock:
        attempts = _auth_failures[key]
        cutoff = now - settings.AUTH_RATE_WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        attempts.append(now)


async def clear_all_auth_failures() -> None:
    """Useful for isolated test suites and local development resets."""
    async with _auth_lock:
        _auth_failures.clear()


def unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
