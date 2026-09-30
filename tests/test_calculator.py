"""Phase 10 tests for the safe calculator tool."""

from pathlib import Path
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.tools.calculator import CalculatorError, calculate  # noqa: E402


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 + 2", 4),
        ("125 * 48", 6000),
        ("15% of 2500", 375),
        ("2 ** 8", 256),
        ("(10 - 4) / 2", 3),
    ],
)
def test_calculate_supports_basic_arithmetic(expression: str, expected: int | float) -> None:
    result = calculate(expression)
    assert result.expression == expression
    assert result.value == expected


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "not arithmetic",
        "__import__('os').system('whoami')",
        "open('secret.txt').read()",
        "[1, 2, 3]",
        "True + 1",
    ],
)
def test_calculate_rejects_invalid_or_unsafe_input(expression: str) -> None:
    with pytest.raises(CalculatorError):
        calculate(expression)


def test_calculate_rejects_division_by_zero_and_oversized_expression() -> None:
    with pytest.raises(CalculatorError, match="failed"):
        calculate("10 / 0")
    with pytest.raises(CalculatorError, match="long"):
        calculate("1" * 201)


def test_calculate_rejects_unbounded_results() -> None:
    with pytest.raises(CalculatorError, match="range"):
        calculate("10 ** 100")
