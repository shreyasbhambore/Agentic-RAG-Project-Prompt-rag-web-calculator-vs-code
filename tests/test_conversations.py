"""Conversation persistence and per-user authorization tests."""

import os
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["JWT_SECRET_KEY"] = "test-secret-that-is-long-enough-for-local-tests"

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, get_db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app, ensure_conversation_message_metadata_schema  # noqa: E402


@pytest.fixture
def conversation_client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        test_engine.dispose()


def register_and_login(client: TestClient, username: str) -> str:
    password = "correct-horse-battery"
    registered = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert registered.status_code == 201
    logged_in = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert logged_in.status_code == 200
    return logged_in.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_existing_conversation_database_gets_agent_and_source_columns() -> None:
    test_engine = create_engine("sqlite://")
    try:
        with test_engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE conversation_messages ("
                    "id VARCHAR(36) PRIMARY KEY, "
                    "conversation_id VARCHAR(36) NOT NULL, "
                    "role VARCHAR(16) NOT NULL, "
                    "content TEXT NOT NULL)"
                )
            )
        ensure_conversation_message_metadata_schema(test_engine)
        columns = {
            column["name"]
            for column in inspect(test_engine).get_columns("conversation_messages")
        }
        assert {"agent", "sources"} <= columns
    finally:
        test_engine.dispose()


def test_conversation_creation_message_persistence_and_retrieval(
    conversation_client: TestClient,
) -> None:
    token = register_and_login(conversation_client, "alice")
    created = conversation_client.post("/api/conversations", headers=auth(token))

    assert created.status_code == 201
    conversation_id = created.json()["id"]
    assert created.json()["created_at"]
    assert created.json()["updated_at"]

    posted = conversation_client.post(
        f"/api/conversations/{conversation_id}/messages",
        headers=auth(token),
        json={"content": "  Keep this message.  ", "role": "assistant"},
    )
    assert posted.status_code == 201
    assert posted.json()["content"] == "  Keep this message.  "
    assert posted.json()["role"] == "user"
    second_posted = conversation_client.post(
        f"/api/conversations/{conversation_id}/messages",
        headers=auth(token),
        json={"content": "A second message."},
    )
    assert second_posted.status_code == 201

    loaded = conversation_client.get(
        f"/api/conversations/{conversation_id}",
        headers=auth(token),
    )
    assert loaded.status_code == 200
    assert [message["content"] for message in loaded.json()["messages"]] == [
        "  Keep this message.  ",
        "A second message.",
    ]

    listed = conversation_client.get("/api/conversations", headers=auth(token))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [conversation_id]


def test_users_cannot_list_read_or_write_another_users_conversations(
    conversation_client: TestClient,
) -> None:
    alice_token = register_and_login(conversation_client, "alice")
    bob_token = register_and_login(conversation_client, "bob")
    created = conversation_client.post("/api/conversations", headers=auth(alice_token))
    conversation_id = created.json()["id"]

    assert conversation_client.get("/api/conversations", headers=auth(bob_token)).json() == []
    assert (
        conversation_client.get(
            f"/api/conversations/{conversation_id}",
            headers=auth(bob_token),
        ).status_code
        == 404
    )
    assert (
        conversation_client.post(
            f"/api/conversations/{conversation_id}/messages",
            headers=auth(bob_token),
            json={"content": "attempted cross-user write"},
        ).status_code
        == 404
    )


def test_user_cannot_escalate_role_by_editing_signed_token_claims(
    conversation_client: TestClient,
) -> None:
    user_token = register_and_login(conversation_client, "alice")
    me = conversation_client.get("/api/auth/me", headers=auth(user_token))
    user_id = me.json()["id"]
    now = datetime.now(timezone.utc)
    settings = get_settings()
    forged_claim_token = jwt.encode(
        {
            "sub": user_id,
            "role": "admin",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = conversation_client.get(
        "/api/auth/me",
        headers=auth(forged_claim_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["role"] == "user"


def test_conversation_endpoints_require_authentication(
    conversation_client: TestClient,
) -> None:
    assert conversation_client.post("/api/conversations").status_code == 401
    assert conversation_client.get("/api/conversations").status_code == 401


@pytest.mark.parametrize("content", ["", "  ", "x" * 10001])
def test_message_endpoint_validates_content(
    conversation_client: TestClient,
    content: str,
) -> None:
    token = register_and_login(conversation_client, "alice")
    conversation = conversation_client.post("/api/conversations", headers=auth(token)).json()
    response = conversation_client.post(
        f"/api/conversations/{conversation['id']}/messages",
        headers=auth(token),
        json={"content": content},
    )
    assert response.status_code == 422
