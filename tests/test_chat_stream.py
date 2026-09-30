"""Authenticated SSE chat endpoint tests."""

import json
import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["JWT_SECRET_KEY"] = "test-secret-that-is-long-enough-for-local-tests"

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.api import chat as chat_api  # noqa: E402
from app.agents import runtime as runtime_module  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


class FakeStreamer:
    def __init__(self, tokens: list[str] | Exception) -> None:
        self.tokens = tokens
        self.messages: list[dict[str, str]] | None = None

    def stream(self, messages: list[dict[str, str]]):
        self.messages = messages
        if isinstance(self.tokens, Exception):
            raise self.tokens
        yield from self.tokens


@pytest.fixture
def chat_client(monkeypatch: pytest.MonkeyPatch):
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
    monkeypatch.setattr(
        chat_api,
        "get_settings",
        lambda: type("Settings", (), {"groq_api_key": "test-key"})(),
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        test_engine.dispose()


def create_token(client: TestClient, username: str) -> str:
    password = "correct-horse-battery"
    assert client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    ).status_code == 201
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_chat_stream_persists_user_and_assistant_and_emits_sse(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamer = FakeStreamer(["Hello", " there"])
    monkeypatch.setattr(runtime_module, "GroqStreamingClient", lambda: streamer)
    token = create_token(chat_client, "alice")

    response = chat_client.post(
        "/api/chat/stream",
        headers=headers(token),
        json={"message": "Hi"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [event["type"] for event in events] == ["token", "token", "done"]
    assert "".join(event.get("token", "") for event in events) == "Hello there"
    assert events[-1]["agent"] == "Groq direct response"
    assert events[-1]["sources"] == []
    conversation_id = events[-1]["conversation_id"]

    history = chat_client.get(
        f"/api/conversations/{conversation_id}",
        headers=headers(token),
    ).json()
    assert [(item["role"], item["content"]) for item in history["messages"]] == [
        ("user", "Hi"),
        ("assistant", "Hello there"),
    ]
    assert history["messages"][1]["agent"] == "Groq direct response"
    assert history["messages"][1]["sources"] == []
    assert streamer.messages == [{"role": "user", "content": "Hi"}]


def test_chat_stream_rejects_unauthorized_conversation_and_invalid_auth(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamer = FakeStreamer(["unused"])
    monkeypatch.setattr(runtime_module, "GroqStreamingClient", lambda: streamer)
    alice = create_token(chat_client, "alice")
    bob = create_token(chat_client, "bob")
    conversation = chat_client.post("/api/conversations", headers=headers(alice)).json()

    cross_user = chat_client.post(
        "/api/chat/stream",
        headers=headers(bob),
        json={"message": "try", "conversation_id": conversation["id"]},
    )
    assert cross_user.status_code == 404
    assert chat_client.post("/api/chat/stream", json={"message": "Hi"}).status_code == 401


def test_chat_stream_reports_provider_failure_without_persisting_assistant(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.llm.groq import GroqStreamError

    monkeypatch.setattr(
        runtime_module,
        "GroqStreamingClient",
        lambda: FakeStreamer(GroqStreamError("private provider details")),
    )
    token = create_token(chat_client, "alice")
    response = chat_client.post(
        "/api/chat/stream",
        headers=headers(token),
        json={"message": "Hi"},
    )

    assert response.status_code == 200
    assert "private provider details" not in response.text
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[-1] == {
        "type": "error",
        "message": (
            "Groq could not complete the request. Check the backend terminal for "
            "its safe failure category, then retry."
        ),
    }
    conversation_id = chat_client.get(
        "/api/conversations",
        headers=headers(token),
    ).json()[0]["id"]
    history = chat_client.get(
        f"/api/conversations/{conversation_id}",
        headers=headers(token),
    ).json()
    assert [item["role"] for item in history["messages"]] == ["user"]


def test_chat_stream_explains_invalid_groq_key_without_exposing_provider_body(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.llm.groq import GroqStreamError

    monkeypatch.setattr(
        runtime_module,
        "GroqStreamingClient",
        lambda: FakeStreamer(
            GroqStreamError(
                "secret-bearing provider body",
                failure_code="unauthorized",
                status_code=401,
            )
        ),
    )
    token = create_token(chat_client, "unauthorized-provider-user")
    response = chat_client.post(
        "/api/chat/stream",
        headers=headers(token),
        json={"message": "Hi"},
    )

    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[-1] == {
        "type": "error",
        "message": (
            "Groq rejected the API key (HTTP 401). Check GROQ_API_KEY in .env; "
            "replace it if it was revoked, and restart FastAPI."
        ),
    }
    assert "secret-bearing provider body" not in response.text


def test_calculator_chat_route_does_not_require_groq_configuration(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_api,
        "get_settings",
        lambda: type("Settings", (), {"groq_api_key": ""})(),
    )
    token = create_token(chat_client, "calculator-user")

    response = chat_client.post(
        "/api/chat/stream",
        headers=headers(token),
        json={"message": "What is 15% of 2500?"},
    )

    assert response.status_code == 200
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[0] == {"type": "token", "token": "15% of 2500 = 375.0"}
    assert events[-1]["agent"] == "Calculator Agent"


def test_web_sources_and_agent_metadata_survive_conversation_reload(
    chat_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.tools.web_search import WebSearchResponse, WebSearchResult

    streamer = FakeStreamer(["A current answer [1]."])
    monkeypatch.setattr(runtime_module, "GroqStreamingClient", lambda: streamer)
    monkeypatch.setattr(
        runtime_module,
        "search_web",
        lambda query: WebSearchResponse(
            query,
            "tavily",
            [WebSearchResult("Current source", "https://example.com", "Evidence", "tavily")],
        ),
    )
    token = create_token(chat_client, "web-user")
    response = chat_client.post(
        "/api/chat/stream",
        headers=headers(token),
        json={"message": "What is the latest news?"},
    )
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    conversation_id = events[-1]["conversation_id"]

    history = chat_client.get(
        f"/api/conversations/{conversation_id}",
        headers=headers(token),
    ).json()
    saved_answer = history["messages"][-1]
    assert saved_answer["agent"] == "Web Search Agent"
    assert saved_answer["sources"] == [
        {
            "title": "Current source",
            "url": "https://example.com",
            "source": "tavily",
        }
    ]


@pytest.mark.parametrize("message", ["", "  ", "x" * 10001])
def test_chat_stream_validates_message(
    chat_client: TestClient,
    message: str,
) -> None:
    token = create_token(chat_client, "alice")
    response = chat_client.post(
        "/api/chat/stream",
        headers=headers(token),
        json={"message": message},
    )
    assert response.status_code == 422
