"""CLI command: sources (list / refresh).

Surfaces the live/static model sources feeding discovery so users can see
where discovered models come from and force a cache refresh. See
Architecture.md §6/§9.
"""

from __future__ import annotations

import typer

from modeldock.cli.console import print_error, render_sources
from modeldock.core.manager import ModelManager

sources_app = typer.Typer(help="Inspect and refresh model sources")


@sources_app.callback(invoke_without_command=True)
def sources_default(
    ctx: typer.Context,
    debug: bool = typer.Option(False, "--debug", help="Show traceback"),
) -> None:
    """List the active model sources (default when no subcommand is given)."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        mgr = ModelManager()
        render_sources(mgr.sources())
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary
        print_error(exc, debug)
        raise typer.Exit(code=1)  # noqa: B904


@sources_app.command("refresh")
def sources_refresh(debug: bool = typer.Option(False, "--debug", help="Show traceback")) -> None:
    """Force each live source to re-fetch, bypassing its cache TTL."""
    try:
        mgr = ModelManager()
        render_sources(mgr.refresh_sources())
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary
        print_error(exc, debug)
        raise typer.Exit(code=1)  # noqa: B904
