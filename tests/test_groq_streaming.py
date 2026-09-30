"""Groq adapter tests using local fake HTTP streams."""

import json
from types import SimpleNamespace
from typing import Iterator

import pytest
import requests

from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.llm.groq import (  # noqa: E402
    GroqConfigurationError,
    GroqStreamError,
    GroqStreamingClient,
)


class FakeResponse:
    def __init__(self, lines: list[str | bytes], error: Exception | None = None) -> None:
        self.lines = lines
        self.error = error
        self.closed = False

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def iter_lines(self, decode_unicode: bool = False) -> Iterator[str | bytes]:
        yield from self.lines

    def close(self) -> None:
        self.closed = True


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.request: dict[str, object] | None = None

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.request = {"url": url, **kwargs}
        return self.response


def sse(payload: object) -> str:
    return f"data: {json.dumps(payload)}"


def test_groq_adapter_yields_content_and_closes_response() -> None:
    response = FakeResponse(
        [
            "event: message",
            sse({"choices": [{"delta": {"content": "Hello"}}]}),
            sse({"choices": [{"delta": {"content": " world"}}]}),
            (
                "data: "
                + json.dumps(
                    {"choices": [{"delta": {"content": " I’m"}}]},
                    ensure_ascii=False,
                )
            ).encode("utf-8"),
            "data: [DONE]",
        ]
    )
    client = FakeHttpClient(response)
    adapter = GroqStreamingClient(
        api_key="test-key",
        model="test-model",
        timeout=2,
        client=client,
    )

    assert list(adapter.stream([{"role": "user", "content": "Hi"}])) == [
        "Hello",
        " world",
        " I’m",
    ]
    assert response.closed
    assert client.request is not None
    assert client.request["url"] == adapter.endpoint
    assert client.request["stream"] is True
    assert client.request["timeout"] == 2
    assert client.request["headers"]["Authorization"] == "Bearer test-key"


def test_groq_adapter_rejects_missing_configuration_and_malformed_streams() -> None:
    with pytest.raises(GroqConfigurationError, match="GROQ_API_KEY"):
        list(GroqStreamingClient(api_key="", client=FakeHttpClient(FakeResponse([]))).stream([]))

    response = FakeResponse(["data: not-json"])
    with pytest.raises(GroqStreamError, match="malformed"):
        list(
            GroqStreamingClient(
                api_key="test-key",
                client=FakeHttpClient(response),
            ).stream([{"role": "user", "content": "Hi"}])
        )
    assert response.closed


def test_groq_adapter_reports_provider_and_http_errors() -> None:
    provider_response = FakeResponse([sse({"error": {"message": "rate limited"}})])
    with pytest.raises(GroqStreamError, match="rate limited"):
        list(
            GroqStreamingClient(
                api_key="test-key",
                client=FakeHttpClient(provider_response),
            ).stream([{"role": "user", "content": "Hi"}])
        )

    http_response = FakeResponse([], requests.HTTPError("private details"))
    with pytest.raises(GroqStreamError, match="request failed") as error:
        GroqStreamingClient(
            api_key="test-key",
            client=FakeHttpClient(http_response),
        ).stream([{"role": "user", "content": "Hi"}])
    assert error.value.failure_code == "request_failed"

    for status_code, expected_category in (
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "not_found"),
        (429, "rate_limited"),
    ):
        provider_error = requests.HTTPError(
            "private details",
            response=SimpleNamespace(status_code=status_code),
        )
        with pytest.raises(GroqStreamError) as error:
            GroqStreamingClient(
                api_key="test-key",
                client=FakeHttpClient(FakeResponse([], provider_error)),
            ).stream([{"role": "user", "content": "Hi"}])
        assert error.value.failure_code == expected_category
        assert error.value.status_code == status_code
        assert "private details" not in str(error.value)
