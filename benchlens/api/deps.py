"""FastAPI dependencies — DB session, current user, RBAC role guard."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from benchlens.api.auth import (
    AuthError,
    ForbiddenError,
    JwtConfig,
    User,
    UserStore,
    decode_access_token,
)
from benchlens.utils.db import get_session_factory

# OAuth2 spec: the client sends `Authorization: Bearer <token>`; tokenUrl is
# the login route exposed below at /auth/login.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Singleton-ish accessors. Built once per process when the app starts; tests
# can override by setting these via dependency_overrides.
_user_store: UserStore | None = None
_jwt_config: JwtConfig | None = None


def init_auth_state(store: UserStore | None = None, jwt_cfg: JwtConfig | None = None) -> None:
    """Wire the auth singletons. Called from the app factory (and tests)."""
    global _user_store, _jwt_config
    _user_store = store or UserStore.from_settings()
    _jwt_config = jwt_cfg or JwtConfig.from_settings()


def get_user_store() -> UserStore:
    if _user_store is None:
        init_auth_state()
    assert _user_store is not None
    return _user_store


def get_jwt_config() -> JwtConfig:
    if _jwt_config is None:
        init_auth_state()
    assert _jwt_config is not None
    return _jwt_config


def get_db() -> Iterator[Session]:
    """Yield a SQLAlchemy session; auto-closed at request end."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def get_current_user(
    token: Annotated[str, Depends(_oauth2_scheme)],
    jwt_cfg: Annotated[JwtConfig, Depends(get_jwt_config)],
    store: Annotated[UserStore, Depends(get_user_store)],
) -> User:
    """Resolve the user from a bearer token. 401 on any failure."""
    try:
        payload = decode_access_token(token, config=jwt_cfg)
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = store.get(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*roles: str):
    """Factory that returns a dependency permitting only the given role(s)."""
    allowed = frozenset(roles)

    def _checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not allowed (need one of {sorted(allowed)}).",
            )
        return user

    return _checker


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]
AdminUser = Annotated[User, Depends(require_role("admin"))]
