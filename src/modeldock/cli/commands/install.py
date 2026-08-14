"""CLI command: install."""

from __future__ import annotations

import typer

from modeldock.cli.console import print_error
from modeldock.cli.factory import manager_for


def install_cmd(
    models: list[str] = typer.Argument(..., help="Model name(s)"),
    backend: str = typer.Option(None, "--backend", help="Runtime backend"),
    debug: bool = typer.Option(False, "--debug", help="Show traceback"),
) -> None:
    """Install one or more models."""
    try:
        mgr = manager_for(backend)
        for name in models:
            ref = mgr.install(name)
            typer.echo(f"Installed {ref.qualified_name()}")
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary
        print_error(exc, debug)
        raise typer.Exit(code=1)  # noqa: B904
