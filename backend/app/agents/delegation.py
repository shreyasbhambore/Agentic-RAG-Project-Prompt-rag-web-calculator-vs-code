"""Bounded multi-agent delegation and synthesis with LangGraph."""

from dataclasses import dataclass
import re
from typing import Protocol, Sequence, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.supervisor import Handler, RouteTarget, SupervisorError


MAX_DELEGATION_STEPS = 3
_MAX_TASK_LENGTH = 4096
_RAG_HINT = re.compile(r"\b(?:book|document|pdf|chapter|page|source|according)\b", re.IGNORECASE)
_WEB_HINT = re.compile(r"\b(?:latest|current|today|news|web|online|search|trends)\b", re.IGNORECASE)
_CALCULATOR_HINT = re.compile(
    r"(?:%\s+of|percentage|calculate|calculation|[0-9]+\s*[+*/^()-]\s*[0-9]+)",
    re.IGNORECASE,
)
_WORKER_TARGETS = {
    RouteTarget.RAG.value: "rag",
    RouteTarget.WEB.value: "web",
    RouteTarget.CALCULATOR.value: "calculator",
}


@dataclass(frozen=True)
class DelegationTask:
    """A bounded, explicit instruction for one specialist worker."""

    target: RouteTarget | str
    question: str


@dataclass(frozen=True)
class DelegationResult:
    """One worker's output retained for final synthesis."""

    target: RouteTarget
    question: str
    output: str


class DelegationState(TypedDict, total=False):
    """Small LangGraph state for a sequential multi-agent workflow."""

    question: str
    user_id: str
    role: str
    plan: list[DelegationTask]
    step_index: int
    results: list[DelegationResult]
    next_target: str
    response: str


class PlanBuilder(Protocol):
    """Create ordered specialist tasks from a user request."""

    def __call__(self, question: str) -> Sequence[DelegationTask]:
        ...


class Synthesizer(Protocol):
    """Combine worker outputs into one user-facing response."""

    def __call__(
        self,
        question: str,
        results: list[DelegationResult],
        user_id: str,
        role: str,
    ) -> str:
        ...


@dataclass(frozen=True)
class DelegationHandlers:
    """Injected specialist workers and final response synthesizer."""

    rag: Handler
    web: Handler
    calculator: Handler
    synthesize: Synthesizer


class DelegationError(SupervisorError):
    """Raised when a delegation plan or worker result is invalid."""


def _validated_question(question: str) -> str:
    if not isinstance(question, str):
        raise DelegationError("question must be text.")
    normalized = question.strip()
    if not normalized:
        raise DelegationError("question must not be empty.")
    if len(normalized) > 4000:
        raise DelegationError("question is too long.")
    return normalized


def default_delegation_plan(question: str) -> list[DelegationTask]:
    """Build an ordered deterministic plan for the capabilities requested."""
    question = _validated_question(question)
    plan: list[DelegationTask] = []
    if _RAG_HINT.search(question):
        plan.append(DelegationTask(RouteTarget.RAG, question))
    if _WEB_HINT.search(question):
        plan.append(DelegationTask(RouteTarget.WEB, question))
    if _CALCULATOR_HINT.search(question):
        plan.append(DelegationTask(RouteTarget.CALCULATOR, question))
    if not plan:
        raise DelegationError("No specialist work was detected for this request.")
    return plan


def _validated_plan(value: Sequence[DelegationTask]) -> list[DelegationTask]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise DelegationError("Delegation planner must return a sequence of tasks.")
    if not value or len(value) > MAX_DELEGATION_STEPS:
        raise DelegationError(f"Delegation plan must contain 1-{MAX_DELEGATION_STEPS} tasks.")

    tasks: list[DelegationTask] = []
    seen: set[RouteTarget] = set()
    for task in value:
        if not isinstance(task, DelegationTask):
            raise DelegationError("Delegation plan contains an invalid task.")
        try:
            target = RouteTarget(str(task.target).strip().upper())
        except (TypeError, ValueError) as error:
            raise DelegationError("Delegation plan contains an unsupported worker.") from error
        if target not in {RouteTarget.RAG, RouteTarget.WEB, RouteTarget.CALCULATOR}:
            raise DelegationError("Delegation plan may only use RAG, WEB, or CALCULATOR workers.")
        if target in seen:
            raise DelegationError("Delegation plan may use each specialist at most once.")
        if not isinstance(task.question, str) or not task.question.strip():
            raise DelegationError("Delegation task question must not be empty.")
        if len(task.question) > _MAX_TASK_LENGTH:
            raise DelegationError("Delegation task question is too long.")
        seen.add(target)
        tasks.append(DelegationTask(target, task.question.strip()))
    return tasks


def build_delegation_graph(
    handlers: DelegationHandlers,
    plan_builder: PlanBuilder = default_delegation_plan,
):
    """Build a sequential worker graph with a strict maximum of three steps."""
    graph = StateGraph(DelegationState)

    def planner_node(state: DelegationState) -> DelegationState:
        question = _validated_question(state["question"])
        plan = _validated_plan(plan_builder(question))
        return {
            "question": question,
            "plan": plan,
            "step_index": 0,
            "results": [],
            "next_target": str(plan[0].target).upper(),
        }

    def next_node(state: DelegationState) -> str:
        next_target = state.get("next_target", "")
        if next_target == "SYNTHESIZE":
            return "synthesize"
        try:
            return _WORKER_TARGETS[RouteTarget(next_target).value]
        except (KeyError, ValueError) as error:
            raise DelegationError("Workflow selected an unsupported next step.") from error

    def worker_node(target: RouteTarget, handler: Handler):
        def execute(state: DelegationState) -> DelegationState:
            index = state["step_index"]
            task = state["plan"][index]
            if RouteTarget(str(task.target).upper()) != target:
                raise DelegationError("Workflow task does not match the selected worker.")
            output = handler(task.question, state["user_id"], state["role"])
            if not isinstance(output, str) or not output.strip():
                raise DelegationError(f"{target.value} worker returned an empty response.")
            result = DelegationResult(target, task.question, output.strip())
            results = [*state["results"], result]
            next_index = index + 1
            next_target = (
                str(state["plan"][next_index].target).upper()
                if next_index < len(state["plan"])
                else "SYNTHESIZE"
            )
            return {
                "step_index": next_index,
                "results": results,
                "next_target": next_target,
            }

        return execute

    def synthesize_node(state: DelegationState) -> DelegationState:
        response = handlers.synthesize(
            state["question"],
            state["results"],
            state["user_id"],
            state["role"],
        )
        if not isinstance(response, str) or not response.strip():
            raise DelegationError("Synthesis returned an empty response.")
        return {"response": response.strip()}

    graph.add_node("planner", planner_node)
    graph.add_node("rag", worker_node(RouteTarget.RAG, handlers.rag))
    graph.add_node("web", worker_node(RouteTarget.WEB, handlers.web))
    graph.add_node("calculator", worker_node(RouteTarget.CALCULATOR, handlers.calculator))
    graph.add_node("synthesize", synthesize_node)
    graph.add_edge(START, "planner")
    destinations = {
        "rag": "rag",
        "web": "web",
        "calculator": "calculator",
        "synthesize": "synthesize",
    }
    graph.add_conditional_edges("planner", next_node, destinations)
    for worker in ("rag", "web", "calculator"):
        graph.add_conditional_edges(worker, next_node, destinations)
    graph.add_edge("synthesize", END)
    return graph.compile()


def run_delegated_workflow(
    handlers: DelegationHandlers,
    question: str,
    user_id: str,
    role: str,
    plan_builder: PlanBuilder = default_delegation_plan,
) -> DelegationState:
    """Execute the bounded specialist workflow for an authenticated user."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise DelegationError("user_id must not be empty.")
    if not isinstance(role, str) or not role.strip():
        raise DelegationError("role must not be empty.")
    graph = build_delegation_graph(handlers, plan_builder)
    return graph.invoke({"question": question, "user_id": user_id, "role": role})
