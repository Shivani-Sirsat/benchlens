"""Unit tests for password hashing + JWT helpers — no DB required."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from benchlens.api.auth import (
    AuthError,
    JwtConfig,
    UserStore,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_round_trip() -> None:
    encoded = hash_password("hunter2")
    assert encoded.startswith("scrypt$")
    assert verify_password("hunter2", encoded) is True
    assert verify_password("wrong", encoded) is False


def test_hash_password_uses_unique_salt() -> None:
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
    assert verify_password("same", a)
    assert verify_password("same", b)


def test_verify_password_rejects_malformed_hash() -> None:
    assert verify_password("x", "not-a-hash") is False
    assert verify_password("x", "scrypt$bad$bad") is False  # non-hex


def test_user_store_authenticate() -> None:
    store = UserStore()
    store.add(username="alice", password="apple", role="admin")
    store.add(username="bob", password="banana", role="viewer")
    assert store.authenticate("alice", "apple").role == "admin"
    assert store.authenticate("bob", "banana").role == "viewer"
    with pytest.raises(AuthError):
        store.authenticate("alice", "wrong")
    with pytest.raises(AuthError):
        store.authenticate("ghost", "x")


def test_user_store_rejects_invalid_role() -> None:
    store = UserStore()
    with pytest.raises(ValueError):
        store.add(username="x", password="x", role="superuser")


def test_jwt_round_trip() -> None:
    store = UserStore()
    user = store.add(username="alice", password="apple", role="admin")
    cfg = JwtConfig(secret="testsecret", algorithm="HS256", expires_minutes=5)
    token, exp = create_access_token(user, config=cfg)
    assert isinstance(token, str) and token.count(".") == 2
    assert exp > datetime.now(timezone.utc)

    payload = decode_access_token(token, config=cfg)
    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"


def test_jwt_rejects_bad_signature() -> None:
    store = UserStore()
    user = store.add(username="alice", password="apple", role="admin")
    good_cfg = JwtConfig(secret="A", algorithm="HS256", expires_minutes=5)
    bad_cfg = JwtConfig(secret="B", algorithm="HS256", expires_minutes=5)
    token, _ = create_access_token(user, config=good_cfg)
    with pytest.raises(AuthError):
        decode_access_token(token, config=bad_cfg)


def test_jwt_rejects_expired_token() -> None:
    store = UserStore()
    user = store.add(username="alice", password="apple", role="admin")
    cfg = JwtConfig(secret="s", algorithm="HS256", expires_minutes=-1)  # already expired
    token, _ = create_access_token(user, config=cfg)
    with pytest.raises(AuthError):
        decode_access_token(token, config=cfg)
