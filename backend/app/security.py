"""Password hashing + JWT helpers.

Used by the seed script (password hashing only) and by the auth router /
deps in the wider backend track (JWT issuance and decoding).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings


# bcrypt is the standard for FastAPI tutorials and is fine for an MVP.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time compare a plaintext password against a stored hash."""
    return _pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str,
    *,
    extra_claims: Optional[Dict[str, Any]] = None,
    expires_minutes: Optional[int] = None,
) -> str:
    """Issue a signed JWT.

    `subject` ends up in the `sub` claim (typically the user id or email).
    `extra_claims` is merged into the payload (e.g. `{"role": "admin"}`).
    """
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(
        minutes=expires_minutes or settings.jwt_expire_minutes
    )
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode + verify a JWT. Raises `JWTError` if invalid or expired."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )


__all__ = [
    "JWTError",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
