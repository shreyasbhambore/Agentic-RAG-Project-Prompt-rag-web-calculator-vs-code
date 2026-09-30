"""Phase 13 tests for bounded multi-agent delegation."""

from pathlib import Path
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.agents.delegation import (  # noqa: E402
    DelegationError,
    DelegationHandlers,
    DelegationTask,
    default_delegation_plan,
    run_delegated_workflow,
)
from app.agents.supervisor import RouteTarget  # noqa: E402


def build_handlers(calls: list[str]) -> DelegationHandlers:
    def worker(name: str):
        def execute(question: str, user_id: str, role: str) -> str:
            calls.append(f"{name}:{user_id}:{role}")
            return f"{name} result for {question}"

        return execute

    def synthesize(question: str, results: list, user_id: str, role: str) -> str:
        calls.append(f"synthesize:{user_id}:{role}")
        return " | ".join(result.output for result in results)

    return DelegationHandlers(
        rag=worker("rag"),
        web=worker("web"),
        calculator=worker("calculator"),
        synthesize=synthesize,
    )


def test_default_plan_delegates_in_order_and_synthesizes_all_results() -> None:
    question = (
        "Explain predictive maintenance from Book 1, compare with current industry "
        "trends, and calculate the percentage difference between 100 and 125."
    )
    calls: list[str] = []
    result = run_delegated_workflow(build_handlers(calls), question, "user-1", "user")

    assert [step.target for step in default_delegation_plan(question)] == [
        RouteTarget.RAG,
        RouteTarget.WEB,
        RouteTarget.CALCULATOR,
    ]
    assert [item.target for item in result["results"]] == [
        RouteTarget.RAG,
        RouteTarget.WEB,
        RouteTarget.CALCULATOR,
    ]
    assert len(result["results"]) == 3
    assert "rag result" in result["response"]
    assert "web result" in result["response"]
    assert "calculator result" in result["response"]
    assert calls == [
        "rag:user-1:user",
        "web:user-1:user",
        "calculator:user-1:user",
        "synthesize:user-1:user",
    ]


def test_custom_plan_runs_only_selected_workers_and_preserves_task_order() -> None:
    calls: list[str] = []
    plan = [
        DelegationTask(RouteTarget.WEB, "search current rates"),
        DelegationTask(RouteTarget.CALCULATOR, "compare 12 and 15"),
    ]
    result = run_delegated_workflow(
        build_handlers(calls),
        "Compare rates.",
        "user-2",
        "admin",
        plan_builder=lambda _: plan,
    )

    assert [item.question for item in result["results"]] == [
        "search current rates",
        "compare 12 and 15",
    ]
    assert calls == [
        "web:user-2:admin",
        "calculator:user-2:admin",
        "synthesize:user-2:admin",
    ]


@pytest.mark.parametrize(
    "plan",
    [
        [],
        [DelegationTask("DIRECT", "respond directly")],
        [DelegationTask(RouteTarget.RAG, "rag"), DelegationTask(RouteTarget.RAG, "again")],
        [
            DelegationTask(RouteTarget.RAG, "rag"),
            DelegationTask(RouteTarget.WEB, "web"),
            DelegationTask(RouteTarget.CALCULATOR, "calc"),
            DelegationTask(RouteTarget.WEB, "too many"),
        ],
        [DelegationTask(RouteTarget.WEB, " ")],
    ],
)
def test_invalid_plan_is_rejected(plan: list[DelegationTask]) -> None:
    with pytest.raises(DelegationError):
        run_delegated_workflow(
            build_handlers([]),
            "Request",
            "user-1",
            "user",
            plan_builder=lambda _: plan,
        )


def test_default_plan_rejects_requests_without_specialist_work() -> None:
    with pytest.raises(DelegationError, match="No specialist work"):
        default_delegation_plan("Hello there")


def test_worker_and_synthesis_failures_are_explicit() -> None:
    handlers = DelegationHandlers(
        rag=lambda *_: "",
        web=lambda *_: "unused",
        calculator=lambda *_: "unused",
        synthesize=lambda *_: "unused",
    )
    with pytest.raises(DelegationError, match="RAG worker"):
        run_delegated_workflow(
            handlers,
            "Book question",
            "user-1",
            "user",
            plan_builder=lambda _: [DelegationTask(RouteTarget.RAG, "question")],
        )

    handlers = DelegationHandlers(
        rag=lambda *_: "evidence",
        web=lambda *_: "unused",
        calculator=lambda *_: "unused",
        synthesize=lambda *_: "",
    )
    with pytest.raises(DelegationError, match="Synthesis"):
        run_delegated_workflow(
            handlers,
            "Book question",
            "user-1",
            "user",
            plan_builder=lambda _: [DelegationTask(RouteTarget.RAG, "question")],
        )
