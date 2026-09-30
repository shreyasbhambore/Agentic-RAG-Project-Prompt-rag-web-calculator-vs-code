"""Authentication behavior and token security tests."""

import os
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
os.environ["JWT_SECRET_KEY"] = "test-secret-that-is-long-enough-for-local-tests"

from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.auth import jwt as jwt_module  # noqa: E402
from app.auth.jwt import create_access_token, decode_token  # noqa: E402
from app.models import Role  # noqa: E402


def test_register_login_refresh_and_current_user(tmp_path: Path) -> None:
    database_path = tmp_path / "auth.db"
    test_engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/auth/register", json={"username": "alice", "password": "correct-horse-battery"}
            )
            assert created.status_code == 201
            assert created.json()["role"] == "user"
            assert "password" not in created.json()

            login = client.post(
                "/api/auth/login", json={"username": "alice", "password": "correct-horse-battery"}
            )
            assert login.status_code == 200
            tokens = login.json()

            me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
            assert me.status_code == 200
            assert me.json()["username"] == "alice"

            refreshed = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
            assert refreshed.status_code == 200
            assert refreshed.json()["access_token"]
    finally:
        app.dependency_overrides.clear()


def test_me_rejects_invalid_token() -> None:
    with TestClient(app) as client:
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401


def test_jwt_signature_tampering_is_rejected(monkeypatch) -> None:
    secret = "security-test-signing-secret"
    monkeypatch.setattr(
        jwt_module,
        "get_settings",
        lambda: SimpleNamespace(
            jwt_secret_key=secret,
            jwt_algorithm="HS256",
            access_token_expire_minutes=30,
        ),
    )
    token = create_access_token("user-1", Role.USER)
    header, payload, signature = token.split(".")
    tampered_signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    tampered = f"{header}.{payload}.{tampered_signature}"

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        decode_token(tampered, expected_type="access")
    assert error.value.status_code == 401


def test_expired_jwt_is_rejected(monkeypatch) -> None:
    secret = "security-test-signing-secret"
    monkeypatch.setattr(
        jwt_module,
        "get_settings",
        lambda: SimpleNamespace(jwt_secret_key=secret, jwt_algorithm="HS256"),
    )
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {
            "sub": "user-1",
            "role": "user",
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        secret,
        algorithm="HS256",
    )

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        decode_token(expired, expected_type="access")
    assert error.value.status_code == 401
