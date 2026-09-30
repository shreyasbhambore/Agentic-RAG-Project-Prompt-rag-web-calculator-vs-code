"""Small, dependency-light client for calling the FastAPI backend."""

import json
import os
from collections.abc import Iterator
from typing import Any

import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


def get_health() -> dict[str, str]:
    """Fetch the backend health state or raise a user-safe request exception."""
    response = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
    response.raise_for_status()
    return response.json()


def login(username: str, password: str) -> dict[str, str]:
    """Exchange credentials for an access and refresh token pair."""
    response = requests.post(
        f"{BACKEND_URL}/api/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def register(username: str, password: str) -> dict[str, str]:
    """Register a normal user account."""
    response = requests.post(
        f"{BACKEND_URL}/api/auth/register",
        json={"username": username, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def get_current_user(access_token: str) -> dict[str, str]:
    """Resolve the authenticated user's server-side identity and role."""
    response = requests.get(
        f"{BACKEND_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def list_conversations(access_token: str) -> list[dict[str, str]]:
    """List the authenticated user's conversations."""
    response = requests.get(
        f"{BACKEND_URL}/api/conversations",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def get_conversation(access_token: str, conversation_id: str) -> dict[str, object]:
    """Retrieve one conversation and its ordered messages."""
    response = requests.get(
        f"{BACKEND_URL}/api/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def stream_chat(
    message: str,
    access_token: str,
    conversation_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield parsed server-sent events from the authenticated chat endpoint."""
    payload: dict[str, str] = {"message": message}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id

    with requests.post(
        f"{BACKEND_URL}/api/chat/stream",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
        stream=True,
        timeout=(5, 120),
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:].strip())
            except json.JSONDecodeError as error:
                raise ValueError("Backend returned malformed streaming data.") from error
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise ValueError("Backend returned an invalid streaming event.")
            yield event
