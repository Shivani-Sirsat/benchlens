"""Authentication + authorization for the BenchLens REST API.

Lightweight by design — single-process JWT auth backed by an in-memory user
table seeded from settings. Production deployments would swap `UserStore`
for a DB-backed implementation; the route handlers and dependencies stay
unchanged.

Password hashing uses stdlib `hashlib.scrypt` — no extra dependency, works
on Python 3.14.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import InvalidTokenError

from benchlens.utils.config_loader import load_config


class AuthError(Exception):
    """Raised for any credential / token problem. Routes map to HTTP 401."""


class ForbiddenError(Exception):
    """Raised when a user is authenticated but lacks the required role."""


# ---------------------------------------------------------------------------
# Password hashing (scrypt)
# ---------------------------------------------------------------------------

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_LEN = 64


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Hash a password with scrypt. Returns 'scrypt$<hex_salt>$<hex_hash>'."""
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_LEN,
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time verification of `password` against a stored hash."""
    try:
        scheme, salt_hex, digest_hex = encoded.split("$", 2)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    candidate = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_LEN,
    )
    try:
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, expected)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

VALID_ROLES: frozenset[str] = frozenset({"admin", "viewer"})


@dataclass(frozen=True, slots=True)
class User:
    username: str
    role: str
    password_hash: str

    def to_public(self) -> dict[str, str]:
        return {"username": self.username, "role": self.role}


class UserStore:
    """In-memory username -> User table. Seeded from settings.yaml on init."""

    def __init__(self, users: dict[str, User] | None = None) -> None:
        self._users: dict[str, User] = dict(users or {})

    @classmethod
    def from_settings(cls) -> UserStore:
        """Build from `api.users` in settings.yaml. Falls back to demo accounts."""
        cfg = load_config("settings")
        api_cfg = cfg.get("api") or {}
        users_cfg = api_cfg.get("users") or []
        store = cls()
        if users_cfg:
            for entry in users_cfg:
                store.add(
                    username=entry["username"],
                    password=entry["password"],
                    role=entry.get("role", "viewer"),
                )
        else:
            # Demo defaults for local dev. Overridden by any users in settings.
            store.add(username="admin", password="admin", role="admin")
            store.add(username="viewer", password="viewer", role="viewer")
        return store

    def add(self, *, username: str, password: str, role: str) -> User:
        if role not in VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(VALID_ROLES)}")
        user = User(username=username, role=role, password_hash=hash_password(password))
        self._users[username] = user
        return user

    def get(self, username: str) -> User | None:
        return self._users.get(username)

    def authenticate(self, username: str, password: str) -> User:
        user = self.get(username)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Invalid username or password.")
        return user


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JwtConfig:
    secret: str
    algorithm: str
    expires_minutes: int

    @classmethod
    def from_settings(cls) -> JwtConfig:
        cfg = load_config("settings")
        jcfg = (cfg.get("api") or {}).get("jwt") or {}
        return cls(
            secret=str(jcfg.get("secret", "change_me")),
            algorithm=str(jcfg.get("algorithm", "HS256")),
            expires_minutes=int(jcfg.get("expires_minutes", 60)),
        )


def create_access_token(user: User, *, config: JwtConfig) -> tuple[str, datetime]:
    """Returns (token, expires_at)."""
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=config.expires_minutes)
    payload: dict[str, Any] = {
        "sub": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, config.secret, algorithm=config.algorithm)
    return token, exp


def decode_access_token(token: str, *, config: JwtConfig) -> dict[str, Any]:
    try:
        return jwt.decode(token, config.secret, algorithms=[config.algorithm])
    except InvalidTokenError as e:
        raise AuthError(f"Invalid token: {e}") from e


__all__ = [
    "AuthError",
    "ForbiddenError",
    "User",
    "UserStore",
    "JwtConfig",
    "VALID_ROLES",
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
]
