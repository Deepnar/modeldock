"""CLI command: update."""

from __future__ import annotations

import typer

from modeldock.cli.console import print_error
from modeldock.cli.factory import manager_for


def update_cmd(
    models: list[str] = typer.Argument(..., help="Model name(s)"),
    backend: str = typer.Option(None, "--backend", help="Runtime backend"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    debug: bool = typer.Option(False, "--debug", help="Show traceback"),
) -> None:
    """Pull a newer tag for installed model(s)."""
    try:
        mgr = manager_for(backend)
        for name in models:
            # update() is destructive (removes, then re-downloads) and refuses
            # to run without confirm=True. Ask here, or take --yes, otherwise
            # the command can never succeed.
            if not yes and not typer.confirm(f"Remove and re-download {name}?"):
                continue
            ref = mgr.update(name, confirm=True)
            typer.echo(f"Updated {ref.qualified_name()}")
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary
        print_error(exc, debug)
        raise typer.Exit(code=1)  # noqa: B904
