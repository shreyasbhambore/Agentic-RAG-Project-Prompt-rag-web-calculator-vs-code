"""Runtime bindings connecting supervisor routes to application services."""

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agents import runtime  # noqa: E402
from app.agents.runtime import AgentIdentity, run_agent_request  # noqa: E402
from app.models import Role  # noqa: E402
from app.rag.hybrid import HybridResult  # noqa: E402
from app.rag.reranking import RerankedResult  # noqa: E402
from app.tools.web_search import WebSearchResponse, WebSearchResult  # noqa: E402


class FakeStreamer:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.messages: list[dict[str, str]] | None = None

    def stream(self, messages: list[dict[str, str]]):
        self.messages = messages
        yield from self.tokens


def test_direct_supervisor_route_streams_and_preserves_conversation_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streamer = FakeStreamer(["Hello", " again"])
    monkeypatch.setattr(runtime, "GroqStreamingClient", lambda: streamer)
    emitted: list[str] = []

    result = run_agent_request(
        "How are you?",
        AgentIdentity("user-1", Role.USER),
        history=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
        on_token=emitted.append,
    )

    assert result.route == "Groq direct response"
    assert result.response == "Hello again"
    assert result.sources == []
    assert emitted == ["Hello", " again"]
    assert streamer.messages == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "How are you?"},
    ]


def test_calculator_route_does_not_require_or_call_groq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_model() -> None:
        raise AssertionError("Calculator route must not create a Groq client.")

    monkeypatch.setattr(runtime, "GroqStreamingClient", unexpected_model)

    result = run_agent_request(
        "What is 15% of 2500?",
        AgentIdentity("user-1", Role.USER),
    )

    assert result.route == "Calculator Agent"
    assert result.response == "15% of 2500 = 375.0"
    assert result.sources == []


def test_web_route_returns_validated_sources_and_streams_grounded_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime,
        "search_web",
        lambda query: WebSearchResponse(
            query,
            "tavily",
            [WebSearchResult("Example", "https://example.com", "Current facts", "tavily")],
        ),
    )
    streamer = FakeStreamer(["A current answer [1]."])
    monkeypatch.setattr(runtime, "GroqStreamingClient", lambda: streamer)
    emitted: list[str] = []

    result = run_agent_request(
        "What is the latest update?",
        AgentIdentity("user-1", Role.USER),
        on_token=emitted.append,
    )

    assert result.route == "Web Search Agent"
    assert result.response == "A current answer [1]."
    assert result.sources == [
        {
            "title": "Example",
            "url": "https://example.com",
            "source": "tavily",
        }
    ]
    assert emitted == ["A current answer [1]."]
    assert "Current facts" in streamer.messages[1]["content"]


def test_rag_route_uses_authenticated_identity_and_returns_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = AgentIdentity("user-1", Role.USER)
    dense_candidate = HybridResult(
        text="Authorized evidence",
        metadata={
            "allowed_user_id": user.id,
            "book_name": "Allowed Book",
            "source": "allowed.pdf",
            "page_number": 7,
            "chunk_id": "chunk-1",
        },
        fused_score=0.1,
        dense_rank=1,
        sparse_rank=1,
    )
    reranked_candidate = RerankedResult(
        text=dense_candidate.text,
        metadata=dense_candidate.metadata,
        rerank_score=0.9,
        fused_score=dense_candidate.fused_score,
        dense_rank=1,
        sparse_rank=1,
    )
    searches: list[tuple[str, str, Role]] = []
    query_embeddings: list[list[float]] = []

    class FakeCollection:
        def count(self) -> int:
            return 1

    class FakeReranker:
        def rerank(self, query, candidates, authenticated_user):
            assert authenticated_user.id == user.id
            assert authenticated_user.role == user.role
            return [reranked_candidate]

    components = SimpleNamespace(
        collection=FakeCollection(),
        embedding_function=lambda _: [[np.float32(0.25), np.float32(0.5)]],
        bm25_index=object(),
        reranker=FakeReranker(),
    )

    def fake_search_hybrid(collection, embedding, bm25, query, authenticated_user):
        query_embeddings.append(embedding)
        searches.append((query, authenticated_user.id, authenticated_user.role))
        return [dense_candidate]

    monkeypatch.setattr(runtime, "_retrieval_components", lambda: components)
    monkeypatch.setattr(
        runtime,
        "search_hybrid",
        fake_search_hybrid,
    )
    streamer = FakeStreamer(["Grounded", " [1]"])
    monkeypatch.setattr(runtime, "GroqStreamingClient", lambda: streamer)
    emitted: list[str] = []

    result = run_agent_request(
        "According to the book, what is stated?",
        user,
        on_token=emitted.append,
    )

    assert result.route == "RAG Agent"
    assert query_embeddings == [[0.25, 0.5]]
    assert all(type(value) is float for value in query_embeddings[0])
    assert result.response == "Grounded [1]"
    assert result.sources == [
        {
            "title": "[1] Allowed Book, allowed.pdf, page 7",
            "source": "allowed.pdf",
            "page_number": "7",
        }
    ]
    assert searches == [
        ("According to the book, what is stated?", user.id, user.role)
    ]
    assert emitted == ["Grounded", " [1]"]
    assert "Authorized evidence" in streamer.messages[1]["content"]


def test_compound_request_runs_bounded_workers_then_synthesizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_searches: list[str] = []

    def fake_search(query: str) -> WebSearchResponse:
        web_searches.append(query)
        return WebSearchResponse(
            query,
            "tavily",
            [WebSearchResult("Latest price", "https://example.com", "Price is 200.", "tavily")],
        )

    monkeypatch.setattr(runtime, "search_web", fake_search)
    streamer = FakeStreamer(["The price is 200; 15% is 30."])
    monkeypatch.setattr(runtime, "GroqStreamingClient", lambda: streamer)
    emitted: list[str] = []

    result = run_agent_request(
        "What is the latest price? Calculate 15% of 200.",
        AgentIdentity("user-1", Role.USER),
        on_token=emitted.append,
    )

    assert result.route == "Multi-agent synthesis"
    assert result.response == "The price is 200; 15% is 30."
    assert web_searches == ["What is the latest price? Calculate 15% of 200."]
    assert result.sources == [
        {
            "title": "Latest price",
            "url": "https://example.com",
            "source": "tavily",
        }
    ]
    assert emitted == ["The price is 200; 15% is 30."]
    assert streamer.messages is not None
    assert "CALCULATOR result" in streamer.messages[-1]["content"]
    assert "30.0" in streamer.messages[-1]["content"]
