"""Phase 11 tests for configurable web search."""

from pathlib import Path
import sys

import pytest
import requests

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.tools.web_search import WebSearchError, search_web  # noqa: E402
from app.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def configured_test_keys() -> None:
    settings = get_settings()
    settings.tavily_api_key = "test-tavily-key"
    settings.serper_api_key = "test-serper-key"


class FakeResponse:
    def __init__(self, payload: object, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def json(self) -> object:
        return self.payload


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, object], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return self.response


def test_tavily_search_returns_structured_sources() -> None:
    client = FakeClient(
        FakeResponse(
            {"results": [{"title": "Example", "url": "https://example.com", "content": "Evidence"}]}
        )
    )

    response = search_web("latest topic", provider="tavily", max_results=3, timeout=2.5, client=client)

    assert response.provider == "tavily"
    assert response.results[0].url == "https://example.com"
    assert response.results[0].source == "tavily"
    assert client.calls[0]["timeout"] == 2.5
    assert client.calls[0]["json"]["query"] == "latest topic"


def test_serper_search_maps_organic_results() -> None:
    client = FakeClient(
        FakeResponse({"organic": [{"title": "Result", "link": "https://example.com", "snippet": "Text"}]})
    )

    response = search_web("query", provider="serper", client=client)

    assert response.provider == "serper"
    assert response.results[0].snippet == "Text"
    assert client.calls[0]["headers"]["X-API-KEY"] != ""


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": ""},
        {"query": "query", "provider": "unknown"},
        {"query": "query", "provider": "tavily", "max_results": 0},
        {"query": "query", "provider": "tavily", "max_results": 21},
        {"query": "query", "provider": "tavily", "timeout": 0},
    ],
)
def test_web_search_rejects_invalid_inputs(kwargs: dict[str, object]) -> None:
    with pytest.raises(WebSearchError):
        search_web(client=FakeClient(FakeResponse({})), **kwargs)


def test_web_search_rejects_missing_key_and_invalid_payload() -> None:
    get_settings().tavily_api_key = ""
    with pytest.raises(WebSearchError, match="TAVILY_API_KEY"):
        search_web("query", provider="tavily", client=FakeClient(FakeResponse({"results": []})))
    get_settings().tavily_api_key = "test-tavily-key"
    with pytest.raises(WebSearchError, match="invalid result"):
        search_web(
            "query",
            provider="tavily",
            client=FakeClient(FakeResponse({"results": "not-a-list"})),
        )


def test_web_search_wraps_provider_failures() -> None:
    client = FakeClient(FakeResponse({}, error=requests.RequestException("network down")))

    with pytest.raises(WebSearchError, match="request failed"):
        search_web("query", provider="tavily", client=client)
