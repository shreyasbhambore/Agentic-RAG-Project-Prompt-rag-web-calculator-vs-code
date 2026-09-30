"""LangGraph supervisor for safe single-step agent routing."""

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Callable, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph


class RouteTarget(StrEnum):
    """The only destinations the supervisor may select."""

    RAG = "RAG"
    WEB = "WEB"
    CALCULATOR = "CALCULATOR"
    DIRECT = "DIRECT"
    DELEGATE = "DELEGATE"


class AgentState(TypedDict, total=False):
    """Small state contract shared by the supervisor and worker nodes."""

    question: str
    user_id: str
    role: str
    route: str
    response: str


class RouteDecider(Protocol):
    """Select a route from normalized user input."""

    def __call__(self, question: str) -> str:
        ...


Handler = Callable[[str, str, str], str]


class SupervisorError(ValueError):
    """Raised when a request or route decision cannot be safely processed."""


@dataclass(frozen=True)
class SupervisorHandlers:
    """Injected worker implementations used by the graph."""

    rag: Handler
    web: Handler
    calculator: Handler
    direct: Handler
    delegate: Handler | None = None


_MAX_QUESTION_LENGTH = 4000
_CALCULATOR_HINT = re.compile(
    r"(?:%\s+of|\b(?:calculate|calculation|compute|percentage)\b|"
    r"[0-9]+\s*[+*/%^()-]\s*[0-9]+)",
    re.IGNORECASE,
)
_WEB_HINT = re.compile(
    r"\b(?:latest|current|today|news|web|online|search|trends)\b",
    re.IGNORECASE,
)
_RAG_HINT = re.compile(r"\b(?:book|document|pdf|chapter|page|source|according)\b", re.IGNORECASE)


def _normalize_question(question: str) -> str:
    if not isinstance(question, str):
        raise SupervisorError("question must be text.")
    normalized = question.strip()
    if not normalized:
        raise SupervisorError("question must not be empty.")
    if len(normalized) > _MAX_QUESTION_LENGTH:
        raise SupervisorError("question is too long.")
    return normalized


def default_route_decider(question: str) -> str:
    """Choose an allowlisted route without requiring a model or network call."""
    specialist_hints = (
        _RAG_HINT.search(question),
        _WEB_HINT.search(question),
        _CALCULATOR_HINT.search(question),
    )
    if sum(hint is not None for hint in specialist_hints) > 1:
        return RouteTarget.DELEGATE.value
    if _CALCULATOR_HINT.search(question):
        return RouteTarget.CALCULATOR.value
    if _WEB_HINT.search(question):
        return RouteTarget.WEB.value
    if _RAG_HINT.search(question):
        return RouteTarget.RAG.value
    return RouteTarget.DIRECT.value


def _validated_route(value: str) -> RouteTarget:
    try:
        return RouteTarget(str(value).strip().upper())
    except (TypeError, ValueError) as error:
        raise SupervisorError("Supervisor selected an unsupported route.") from error


def _worker_node(handler: Handler, state: AgentState) -> AgentState:
    question = _normalize_question(state["question"])
    response = handler(question, state["user_id"], state["role"])
    if not isinstance(response, str) or not response.strip():
        raise SupervisorError("Agent handler returned an empty response.")
    return {"response": response.strip()}


def build_supervisor(
    handlers: SupervisorHandlers,
    route_decider: RouteDecider = default_route_decider,
):
    """Build and compile the LangGraph supervisor with injected workers."""

    graph = StateGraph(AgentState)

    def supervisor_node(state: AgentState) -> AgentState:
        question = _normalize_question(state["question"])
        route = _validated_route(route_decider(question))
        return {"question": question, "route": route.value}

    def route_next(state: AgentState) -> str:
        return _validated_route(state.get("route", "")).value

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("rag", lambda state: _worker_node(handlers.rag, state))
    graph.add_node("web", lambda state: _worker_node(handlers.web, state))
    graph.add_node("calculator", lambda state: _worker_node(handlers.calculator, state))
    graph.add_node("direct", lambda state: _worker_node(handlers.direct, state))
    delegate_handler = handlers.delegate or _missing_delegate_handler
    graph.add_node("delegate", lambda state: _worker_node(delegate_handler, state))
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_next,
        {
            RouteTarget.RAG.value: "rag",
            RouteTarget.WEB.value: "web",
            RouteTarget.CALCULATOR.value: "calculator",
            RouteTarget.DIRECT.value: "direct",
            RouteTarget.DELEGATE.value: "delegate",
        },
    )
    for node in ("rag", "web", "calculator", "direct", "delegate"):
        graph.add_edge(node, END)
    return graph.compile()


def _missing_delegate_handler(question: str, user_id: str, role: str) -> str:
    raise SupervisorError("Multi-agent delegation is not configured.")


def run_supervisor(
    handlers: SupervisorHandlers,
    question: str,
    user_id: str,
    role: str,
    route_decider: RouteDecider = default_route_decider,
) -> AgentState:
    """Run one bounded supervisor turn for an authenticated user."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise SupervisorError("user_id must not be empty.")
    if not isinstance(role, str) or not role.strip():
        raise SupervisorError("role must not be empty.")
    graph = build_supervisor(handlers, route_decider)
    return graph.invoke(
        {"question": question, "user_id": user_id, "role": role}
    )
