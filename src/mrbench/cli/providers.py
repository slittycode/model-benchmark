"""Providers command for mrbench.

Lists detected providers/adapters.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mrbench.adapters.registry import get_default_registry

console = Console()


def providers_command(
    all_providers: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show all providers including undetected"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """List detected providers/adapters."""
    registry = get_default_registry()

    providers = []
    for adapter in registry.list_all():
        detection = adapter.detect()

        if not all_providers and not detection.detected:
            continue

        providers.append(
            {
                "name": adapter.name,
                "display_name": adapter.display_name,
                "detected": detection.detected,
                "version": detection.version if detection.detected else None,
                "offline": adapter.get_capabilities().offline,
            }
        )

    if json_output:
        console.print(json.dumps(providers, indent=2))
        return

    if not providers:
        console.print("[yellow]No providers detected. Run 'mrbench doctor' for details.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Status")
    table.add_column("Type")
    table.add_column("Version")

    for p in providers:
        status = "[green]available[/green]" if p["detected"] else "[dim]not found[/dim]"
        ptype = "[blue]local[/blue]" if p["offline"] else "[magenta]cloud[/magenta]"
        version = p.get("version") or "-"
        table.add_row(p["name"], p["display_name"], status, ptype, version)

    console.print(table)
