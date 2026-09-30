"""Security regression checks for unsafe calculator inputs and leaked API keys."""

from pathlib import Path
import re
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.tools.calculator import CalculatorError, calculate  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CREDENTIAL_PATTERNS = (
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\btvly-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{24,}\b"),
)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo compromised')",
        "open('secrets.txt').read()",
        "lambda: 1",
        "2 ** 100000000",
    ],
)
def test_calculator_rejects_tool_misuse(expression: str) -> None:
    with pytest.raises(CalculatorError):
        calculate(expression)


def test_project_source_and_examples_contain_no_provider_api_keys() -> None:
    scanned_files = [
        *PROJECT_ROOT.joinpath("backend", "app").rglob("*.py"),
        *PROJECT_ROOT.joinpath("frontend").rglob("*.py"),
        *PROJECT_ROOT.joinpath("scripts").rglob("*.py"),
        *PROJECT_ROOT.joinpath("tests").rglob("*.py"),
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "COMMANDS.md",
        PROJECT_ROOT / ".env.example",
    ]
    leaked_files: list[str] = []
    for path in scanned_files:
        if not path.is_file():
            continue
        contents = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(contents) for pattern in _CREDENTIAL_PATTERNS):
            leaked_files.append(str(path.relative_to(PROJECT_ROOT)))

    assert leaked_files == []
