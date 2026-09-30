"""Safe arithmetic calculator with no eval or arbitrary code execution."""

import ast
from dataclasses import dataclass
import math
import operator
import re
from typing import Final


class CalculatorError(ValueError):
    """Raised when a calculator expression is invalid or unsafe."""


@dataclass(frozen=True)
class CalculationResult:
    """A normalized calculation result."""

    expression: str
    value: int | float


_BINARY_OPERATORS: Final[dict[type[ast.operator], object]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPERATORS: Final[dict[type[ast.unaryop], object]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_PERCENTAGE_PATTERN = re.compile(
    r"^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*%\s+of\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*$",
    re.IGNORECASE,
)
_MAX_EXPRESSION_LENGTH = 200
_MAX_ABS_VALUE = 1_000_000_000_000_000


def _check_number(value: int | float) -> int | float:
    if not math.isfinite(float(value)) or abs(value) > _MAX_ABS_VALUE:
        raise CalculatorError("Calculation result is outside the supported range.")
    return value


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(
        node.value, bool
    ):
        return _check_number(node.value)
    if isinstance(node, ast.UnaryOp):
        operation = _UNARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise CalculatorError("Unsupported unary operator.")
        return _check_number(operation(_evaluate(node.operand)))  # type: ignore[operator]
    if isinstance(node, ast.BinOp):
        operation = _BINARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise CalculatorError("Unsupported binary operator.")
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        try:
            return _check_number(operation(left, right))  # type: ignore[operator]
        except (ArithmeticError, OverflowError) as error:
            raise CalculatorError("Calculation failed.") from error
    raise CalculatorError("Only numeric arithmetic expressions are supported.")


def calculate(expression: str) -> CalculationResult:
    """Evaluate basic arithmetic and percentage-of expressions safely."""
    if not isinstance(expression, str) or not expression.strip():
        raise CalculatorError("Expression must not be empty.")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise CalculatorError("Expression is too long.")

    percentage = _PERCENTAGE_PATTERN.fullmatch(expression)
    if percentage:
        percent, amount = (float(value) for value in percentage.groups())
        return CalculationResult(expression, _check_number(percent * amount / 100))

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise CalculatorError("Expression is not valid arithmetic.") from error
    return CalculationResult(expression, _evaluate(tree))
