"""Groq chat-completion streaming adapter using its OpenAI-compatible API."""

import json
from typing import Any, Iterator, Protocol, Sequence

import requests

from app.config import get_settings


class GroqConfigurationError(RuntimeError):
    """Raised when Groq streaming configuration is incomplete."""


class GroqStreamError(RuntimeError):
    """Raised when a Groq streaming response is unavailable or malformed."""

    def __init__(
        self,
        message: str,
        *,
        failure_code: str = "provider_error",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.status_code = status_code


class StreamResponseLike(Protocol):
    def raise_for_status(self) -> None:
        ...

    def iter_lines(self, decode_unicode: bool = False) -> Iterator[str | bytes]:
        ...

    def close(self) -> None:
        ...


class HttpClientLike(Protocol):
    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        stream: bool,
        timeout: float,
    ) -> StreamResponseLike:
        ...


def _provider_error(payload: Any) -> str:
    error = payload.get("error") if isinstance(payload, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    return message if isinstance(message, str) else "Groq returned an error event."


class GroqStreamingClient:
    """Yield streamed content deltas from a configured Groq deployment."""

    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: HttpClientLike | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.groq_api_key
        self.model = model if model is not None else settings.groq_model
        self.timeout = timeout if timeout is not None else settings.groq_timeout_seconds
        self.client = client or requests

    def stream(self, messages: Sequence[dict[str, str]]) -> Iterator[str]:
        if not self.api_key.strip():
            raise GroqConfigurationError("GROQ_API_KEY is not configured.")
        if not self.model.strip():
            raise GroqConfigurationError("GROQ_MODEL must not be empty.")
        if self.timeout <= 0:
            raise GroqConfigurationError("GROQ_TIMEOUT_SECONDS must be greater than zero.")
        if not messages:
            raise ValueError("At least one chat message is required.")

        try:
            response = self.client.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "messages": list(messages), "stream": True},
                stream=True,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            response = getattr(error, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code == 401:
                failure_code = "unauthorized"
            elif status_code == 403:
                failure_code = "forbidden"
            elif status_code == 404:
                failure_code = "not_found"
            elif status_code == 429:
                failure_code = "rate_limited"
            elif isinstance(error, requests.Timeout):
                failure_code = "timeout"
            elif isinstance(error, requests.ConnectionError):
                failure_code = "network"
            else:
                failure_code = "request_failed"
            raise GroqStreamError(
                "Groq chat request failed.",
                failure_code=failure_code,
                status_code=status_code,
            ) from error
        except (OSError, TimeoutError) as error:
            raise GroqStreamError(
                "Groq chat request failed.",
                failure_code="network",
            ) from error

        def read_tokens() -> Iterator[str]:
            try:
                for line in response.iter_lines(decode_unicode=False):
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="strict")
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError as error:
                        raise GroqStreamError(
                            "Groq returned malformed streaming data.",
                            failure_code="invalid_response",
                        ) from error
                    if isinstance(payload, dict) and "error" in payload:
                        raise GroqStreamError(
                            _provider_error(payload),
                            failure_code="provider_error",
                        )
                    choices = payload.get("choices") if isinstance(payload, dict) else None
                    if not isinstance(choices, list) or not choices:
                        raise GroqStreamError(
                            "Groq returned an invalid streaming choice.",
                            failure_code="invalid_response",
                        )
                    delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
                    content = delta.get("content") if isinstance(delta, dict) else None
                    if content is None:
                        continue
                    if not isinstance(content, str):
                        raise GroqStreamError(
                            "Groq returned invalid token content.",
                            failure_code="invalid_response",
                        )
                    if content:
                        yield content
            except (
                requests.RequestException,
                OSError,
                TimeoutError,
                UnicodeDecodeError,
            ) as error:
                failure_code = (
                    "timeout"
                    if isinstance(error, (requests.Timeout, TimeoutError))
                    else "network"
                )
                raise GroqStreamError(
                    "Groq stream was interrupted.",
                    failure_code=failure_code,
                ) from error
            finally:
                response.close()

        return read_tokens()
