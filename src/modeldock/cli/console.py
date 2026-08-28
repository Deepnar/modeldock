"""Shared CLI output helpers (rich tables, error formatting)."""

from __future__ import annotations

from typing import Any, List

from modeldock.common.errors import ModelDockError


def print_error(exc: Exception, debug: bool = False) -> None:
    """Print a friendly error to stderr; full traceback in debug mode."""
    import sys

    if isinstance(exc, ModelDockError):
        sys.stderr.write(f"Error: {exc.message}\n")
    else:
        sys.stderr.write(f"Error: {exc}\n")
    if debug:
        import traceback

        traceback.print_exc()


def render_models(models: List[Any]) -> None:
    """Render a list of ModelSpec as a rich table."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Models")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Capabilities")
    table.add_column("Default Tag")
    table.add_column("Source")
    for spec in models:
        table.add_row(
            spec.name,
            spec.category.value,
            ", ".join(c.value for c in spec.capabilities),
            spec.default_tag,
            getattr(spec, "source", None) or "-",
        )
    console.print(table)


def render_installed(refs: List[Any]) -> None:
    """Render installed ModelRefs as a rich table."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Installed Models")
    table.add_column("Name")
    table.add_column("Tag")
    table.add_column("Backend")
    for ref in refs:
        table.add_row(ref.name, ref.tag, ref.backend.value if ref.backend else "-")
    console.print(table)


def render_sources(sources: List[Any]) -> None:
    """Render active model sources (SourceInfo) as a rich table."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Model Sources")
    table.add_column("Source")
    table.add_column("Trust")
    table.add_column("Kind")
    table.add_column("Backend")
    table.add_column("Models", justify="right")
    table.add_column("Status")
    for info in sources:
        table.add_row(
            info.name,
            info.trust.value,
            "live" if info.live else "static",
            info.backend.value if info.backend else "-",
            str(info.model_count),
            "ready" if info.available else "empty",
        )
    console.print(table)


__all__ = ["print_error", "render_models", "render_installed", "render_sources"]
