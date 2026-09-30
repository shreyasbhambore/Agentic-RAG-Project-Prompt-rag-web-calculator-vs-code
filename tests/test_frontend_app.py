"""Streamlit app smoke tests for authentication and the chat interface."""

from pathlib import Path
import sys

import pytest
from streamlit.testing.v1 import AppTest

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
sys.path.insert(0, str(FRONTEND_DIR))


def test_login_and_registration_forms_render() -> None:
    app = AppTest.from_file(str(FRONTEND_DIR / "app.py")).run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Log in", "Create account"]
    assert any(button.label == "Log in" for button in app.button)
    assert any(button.label == "Create account" for button in app.button)


def test_authenticated_chat_history_sources_and_logout_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api_client

    monkeypatch.setattr(api_client, "list_conversations", lambda _token: [])
    monkeypatch.setattr(
        api_client,
        "get_health",
        lambda: {"service": "Agentic RAG", "environment": "test"},
    )
    app = AppTest.from_file(str(FRONTEND_DIR / "app.py"))
    app.session_state["access_token"] = "test-access-token"
    app.session_state["current_user"] = {"username": "alice", "role": "user"}
    app.session_state["chat_messages"] = [
        {
            "role": "assistant",
            "content": "A direct response.",
            "agent": "Groq direct response",
            "sources": [],
        }
    ]
    app.session_state["conversation_id"] = None
    app.session_state["loaded_conversation_id"] = None
    app.run()

    assert not app.exception
    assert any(button.label == "Log out" for button in app.button)
    assert any(selectbox.label == "Your conversations" for selectbox in app.selectbox)
    assert any(chat_input.placeholder == "Ask a question" for chat_input in app.chat_input)
    assert any(expander.label == "Sources" for expander in app.expander)
    assert any("Groq direct response" in caption.value for caption in app.caption)

    logout_button = next(button for button in app.button if button.label == "Log out")
    logout_button.click().run()
    assert not app.exception
    assert "access_token" not in app.session_state
    assert [tab.label for tab in app.tabs] == ["Log in", "Create account"]


def test_reloaded_conversation_uses_persisted_agent_and_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api_client

    monkeypatch.setattr(
        api_client,
        "list_conversations",
        lambda _token: [{"id": "conversation-1", "updated_at": "2026-09-30T12:00:00"}],
    )
    monkeypatch.setattr(
        api_client,
        "get_conversation",
        lambda _token, _conversation_id: {
            "messages": [
                {
                    "role": "assistant",
                    "content": "A sourced answer [1].",
                    "agent": "Web Search Agent",
                    "sources": [
                        {
                            "title": "Current source",
                            "url": "https://example.com",
                            "source": "tavily",
                        }
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        api_client,
        "get_health",
        lambda: {"service": "Agentic RAG", "environment": "test"},
    )
    app = AppTest.from_file(str(FRONTEND_DIR / "app.py"))
    app.session_state["access_token"] = "test-access-token"
    app.session_state["current_user"] = {"username": "alice", "role": "user"}
    app.session_state["chat_messages"] = []
    app.session_state["conversation_id"] = None
    app.session_state["loaded_conversation_id"] = None
    app.run()

    app.selectbox[0].select("conversation-1").run()

    assert not app.exception
    assert any("Web Search Agent" in caption.value for caption in app.caption)
    assert any("Current source" in markdown.value for markdown in app.markdown)
