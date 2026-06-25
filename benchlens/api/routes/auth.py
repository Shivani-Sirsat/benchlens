"""Authentication endpoints — OAuth2 password-flow compatible."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from benchlens.api.auth import AuthError, JwtConfig, UserStore, create_access_token
from benchlens.api.deps import CurrentUser, get_jwt_config, get_user_store
from benchlens.api.schemas import TokenOut, UserOut

router = APIRouter()


@router.post("/login", response_model=TokenOut)
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    store: Annotated[UserStore, Depends(get_user_store)],
    jwt_cfg: Annotated[JwtConfig, Depends(get_jwt_config)],
) -> TokenOut:
    """Exchange username + password for a JWT access token."""
    try:
        user = store.authenticate(form_data.username, form_data.password)
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    token, exp = create_access_token(user, config=jwt_cfg)
    return TokenOut(
        access_token=token,
        token_type="bearer",
        expires_at=exp,
        role=user.role,
        username=user.username,
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    """Return the authenticated caller's identity."""
    return UserOut(username=user.username, role=user.role)
