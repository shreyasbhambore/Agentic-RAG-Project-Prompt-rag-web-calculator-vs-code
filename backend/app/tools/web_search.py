"""Configurable web-search tool with explicit providers and bounded requests."""

from dataclasses import dataclass
from typing import Any, Protocol

import requests

from app.config import get_settings


class WebSearchError(RuntimeError):
    """Raised when web search cannot return a valid provider response."""


class HttpClientLike(Protocol):
    """Small HTTP client surface used by the provider implementations."""

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float) -> Any:
        ...


@dataclass(frozen=True)
class WebSearchResult:
    """One externally sourced search result."""

    title: str
    url: str
    snippet: str
    source: str


@dataclass(frozen=True)
class WebSearchResponse:
    """Bounded search response with provider identity."""

    query: str
    provider: str
    results: list[WebSearchResult]


def _required_key(value: str, name: str) -> str:
    if not value.strip():
        raise WebSearchError(f"{name} is not configured.")
    return value


def _result_list(payload: Any, key: str) -> list[dict[str, Any]]:
    values = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(values, list):
        raise WebSearchError("Web search provider returned an invalid result payload.")
    return [item for item in values if isinstance(item, dict)]


def _result(item: dict[str, Any], provider: str) -> WebSearchResult | None:
    title = item.get("title")
    url = item.get("url") or item.get("link")
    snippet = item.get("content") or item.get("snippet") or ""
    if not isinstance(title, str) or not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None
    return WebSearchResult(
        title=title.strip(),
        url=url.strip(),
        snippet=snippet.strip() if isinstance(snippet, str) else "",
        source=provider,
    )


def _check_response(response: Any) -> Any:
    try:
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError, AttributeError) as error:
        raise WebSearchError("Web search provider request failed.") from error


def _search_tavily(
    query: str, api_key: str, max_results: int, timeout: float, client: HttpClientLike
) -> list[WebSearchResult]:
    payload = _check_response(
        client.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False,
            },
            timeout=timeout,
        )
    )
    return [result for item in _result_list(payload, "results") if (result := _result(item, "tavily"))]


def _search_serper(
    query: str, api_key: str, max_results: int, timeout: float, client: HttpClientLike
) -> list[WebSearchResult]:
    payload = _check_response(
        client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
            timeout=timeout,
        )
    )
    return [result for item in _result_list(payload, "organic") if (result := _result(item, "serper"))]


def search_web(
    query: str,
    *,
    provider: str | None = None,
    max_results: int | None = None,
    timeout: float | None = None,
    client: HttpClientLike | None = None,
) -> WebSearchResponse:
    """Search the configured provider and return validated external sources."""
    settings = get_settings()
    normalized_query = query.strip() if isinstance(query, str) else ""
    if not normalized_query:
        raise WebSearchError("Search query must not be empty.")

    selected_provider = (provider or settings.web_search_provider).strip().casefold()
    result_limit = max_results if max_results is not None else settings.web_search_max_results
    request_timeout = timeout if timeout is not None else settings.web_search_timeout_seconds
    if selected_provider not in {"tavily", "serper"}:
        raise WebSearchError("WEB_SEARCH_PROVIDER must be 'tavily' or 'serper'.")
    if result_limit <= 0 or result_limit > 20:
        raise WebSearchError("max_results must be between 1 and 20.")
    if request_timeout <= 0:
        raise WebSearchError("timeout must be greater than zero.")

    http_client = client or requests
    if selected_provider == "tavily":
        results = _search_tavily(
            normalized_query,
            _required_key(settings.tavily_api_key, "TAVILY_API_KEY"),
            result_limit,
            request_timeout,
            http_client,
        )
    else:
        results = _search_serper(
            normalized_query,
            _required_key(settings.serper_api_key, "SERPER_API_KEY"),
            result_limit,
            request_timeout,
            http_client,
        )
    return WebSearchResponse(normalized_query, selected_provider, results[:result_limit])
