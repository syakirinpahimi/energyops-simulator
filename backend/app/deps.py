"""FastAPI dependencies: current user, role gates."""
from __future__ import annotations

from typing import Iterable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import JWTError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def _unauth(message: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "UNAUTHENTICATED", "message": message}},
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a Bearer JWT."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauth()
    try:
        payload = decode_access_token(creds.credentials)
    except JWTError as exc:
        raise _unauth(f"Invalid token: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise _unauth("Token missing subject")
    try:
        user_id = UUID(sub)
    except ValueError as exc:
        raise _unauth("Token subject is not a UUID") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauth("User not found or inactive")
    return user


def require_role(*roles: str):
    """Dependency factory that asserts the current user holds one of the given roles."""
    allowed = set(roles)

    def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": f"Role '{user.role}' lacks permission",
                        "details": {"required_any_of": sorted(allowed)},
                    }
                },
            )
        return user

    return _checker


def roles_at_least(level: str):
    """Convenience: 'operator' < 'engineer' < 'manager' < 'admin'."""
    order: list[str] = ["operator", "engineer", "manager", "admin"]
    if level not in order:
        raise ValueError(f"Unknown role level: {level}")
    allowed = order[order.index(level):]
    return require_role(*allowed)


__all__ = ["get_current_user", "require_role", "roles_at_least", "bearer_scheme"]


def _ensure_iterable_roles(roles: Iterable[str]) -> tuple[str, ...]:
    return tuple(roles)
