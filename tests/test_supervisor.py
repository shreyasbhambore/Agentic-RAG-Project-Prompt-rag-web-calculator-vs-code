"""Phase 12 tests for LangGraph supervisor routing."""

from pathlib import Path
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agents.supervisor import (  # noqa: E402
    RouteTarget,
    SupervisorError,
    SupervisorHandlers,
    default_route_decider,
    run_supervisor,
)


def handlers(calls: list[str]) -> SupervisorHandlers:
    def make(name: str):
        def handler(question: str, user_id: str, role: str) -> str:
            calls.append(f"{name}:{user_id}:{role}")
            return f"{name} handled: {question}"

        return handler

    return SupervisorHandlers(
        rag=make("rag"),
        web=make("web"),
        calculator=make("calculator"),
        direct=make("direct"),
        delegate=make("delegate"),
    )


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        (RouteTarget.RAG.value, "rag"),
        (RouteTarget.WEB.value, "web"),
        (RouteTarget.CALCULATOR.value, "calculator"),
        (RouteTarget.DIRECT.value, "direct"),
        (RouteTarget.DELEGATE.value, "delegate"),
    ],
)
def test_supervisor_dispatches_only_selected_worker(route: str, expected: str) -> None:
    calls: list[str] = []
    result = run_supervisor(
        handlers(calls),
        "question",
        "user-1",
        "user",
        route_decider=lambda _: route,
    )

    assert result["route"] == route
    assert result["response"].startswith(f"{expected} handled:")
    assert calls == [f"{expected}:user-1:user"]


def test_default_route_decider_covers_expected_request_types() -> None:
    assert default_route_decider("What does the book say?") == RouteTarget.RAG
    assert default_route_decider("What is the latest web news?") == RouteTarget.WEB
    assert default_route_decider("15% of 2500") == RouteTarget.CALCULATOR
    assert (
        default_route_decider(
            "According to the book, what is the latest price and calculate 15% of 2500?"
        )
        == RouteTarget.DELEGATE
    )
    assert default_route_decider("Hello there") == RouteTarget.DIRECT


def test_supervisor_rejects_invalid_route_and_input() -> None:
    with pytest.raises(SupervisorError, match="unsupported route"):
        run_supervisor(handlers([]), "question", "user-1", "user", lambda _: "UNKNOWN")
    with pytest.raises(SupervisorError, match="empty"):
        run_supervisor(handlers([]), " ", "user-1", "user")


def test_supervisor_rejects_empty_worker_output() -> None:
    empty = SupervisorHandlers(
        rag=lambda *_: "",
        web=lambda *_: "unused",
        calculator=lambda *_: "unused",
        direct=lambda *_: "unused",
    )
    with pytest.raises(SupervisorError, match="empty response"):
        run_supervisor(empty, "book question", "user-1", "user", lambda _: RouteTarget.RAG)
