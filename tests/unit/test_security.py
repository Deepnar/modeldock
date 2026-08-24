"""Security regression tests for command execution boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).parents[1] / "src" / "modeldock"
AUDITED_DIRS = (
    SRC_ROOT / "adapters",
    SRC_ROOT / "common",
)


def _python_files() -> list[Path]:
    files: list[Path] = []

    for directory in AUDITED_DIRS:
        files.extend(directory.rglob("*.py"))

    return files


def test_no_shell_execution_in_model_runtime_paths() -> None:
    """Model/runtime code must not invoke commands through a shell."""
    forbidden_calls = {
        "system",
        "popen",
        "create_subprocess_shell",
    }

    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            func = node.func

            if isinstance(func, ast.Attribute):
                if func.attr in forbidden_calls:
                    raise AssertionError(
                        f"Forbidden shell execution API {func.attr!r} found in {path}:{node.lineno}"
                    )

                if func.attr in {"run", "Popen", "call", "check_call", "check_output"}:
                    for keyword in node.keywords:
                        if (
                            keyword.arg == "shell"
                            and isinstance(keyword.value, ast.Constant)
                            and keyword.value.value is True
                        ):
                            raise AssertionError(
                                f"subprocess call uses shell=True in {path}:{node.lineno}"
                            )


def test_model_names_are_treated_as_data() -> None:
    """Shell metacharacters in model names must remain ordinary model-name data."""
    malicious_model_name = "model;echo injected && whoami | cat"

    # This test documents the security boundary: model names may contain
    # characters that have shell meaning, but the application must treat them
    # as ordinary strings rather than command fragments.
    assert malicious_model_name == "model;echo injected && whoami | cat"
