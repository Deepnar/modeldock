"""Unit tests for common/logging defensive validation.

Ensures configure_logging never crashes on bad input and always resolves to a
valid level, so framework objects (e.g. Typer OptionInfo) or invalid strings
never propagate from the CLI layer. See Architecture.md S12.
"""

from __future__ import annotations

import logging

from modeldock.common.logging import configure_logging, get_logger


def _reset_logger() -> None:
    logging.getLogger("modeldock").handlers.clear()


def test_default_level_is_error() -> None:
    _reset_logger()
    logger = configure_logging()
    assert logger.level == logging.ERROR


def test_explicit_valid_level() -> None:
    _reset_logger()
    logger = configure_logging(level="DEBUG")
    assert logger.level == logging.DEBUG


def test_case_insensitive_level() -> None:
    _reset_logger()
    logger = configure_logging(level="warning")
    assert logger.level == logging.WARNING


def test_invalid_level_falls_back_to_info() -> None:
    _reset_logger()
    logger = configure_logging(level="VERBOSE")
    assert logger.level == logging.INFO


def test_non_string_level_falls_back_to_info() -> None:
    # Simulates an OptionInfo descriptor leaking past the CLI layer.
    _reset_logger()
    logger = configure_logging(level=object())  # type: ignore[arg-type]
    assert logger.level == logging.INFO


def test_get_logger_returns_modeldock_child() -> None:
    child = get_logger("cli")
    assert child.name == "modeldock.cli"
    assert get_logger().name == "modeldock"


def test_import_does_not_add_root_handlers() -> None:
    """Importing modeldock must not add handlers to the root logger."""
    import sys

    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k.startswith("modeldock")}
    root_handlers_before = logging.root.handlers[:]
    logging.root.handlers.clear()

    try:
        import modeldock  # noqa: F401

        assert logging.root.handlers == [], (
            f"modeldock polluted the root logger: {logging.root.handlers}"
        )
    finally:
        logging.root.handlers[:] = root_handlers_before
        sys.modules.update(saved)
