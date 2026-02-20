"""Providers command for mrbench.

Lists detected providers/adapters.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

import typer
from rich.console import Console
from rich.table import Table

from mrbench.adapters.registry import get_default_registry
from mrbench.cli._output import emit_json

console = Console()


class ProviderEntry(TypedDict):
    """Provider details displayed in the providers table/JSON output."""

    name: str
    display_name: str
    detected: bool
    version: str | None
    offline: bool


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
    """List detected providers/adapters.

    Use --all to see all available adapters including those not yet detected.

    For API providers (openai, anthropic), you may need to install the api extra:
        pip install mrbench[api]

    Then set your API key:
        export OPENAI_API_KEY=sk-...
        export ANTHROPIC_API_KEY=sk-ant-...
    """
    registry = get_default_registry()

    providers: list[ProviderEntry] = []
    for adapter in registry.list_all():
        detection = adapter.detect()

        if not all_providers and not detection.detected:
            continue

        providers.append(
            ProviderEntry(
                name=adapter.name,
                display_name=adapter.display_name,
                detected=detection.detected,
                version=detection.version if detection.detected else None,
                offline=adapter.get_capabilities().offline,
            )
        )

    if json_output:
        emit_json(providers)
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
        version = p["version"] if p["version"] is not None else "-"
        table.add_row(p["name"], p["display_name"], status, ptype, version)

    console.print(table)

    # Show hints for missing API providers
    api_providers = ["openai", "anthropic"]
    missing_api = [p for p in providers if p["name"] in api_providers and not p["detected"]]
    if missing_api:
        console.print("\n[yellow]Tip: For API providers, install the api extra:[/yellow]")
        console.print("  [cyan]pip install mrbench[api][/cyan]")
        console.print("Then set your API key:")
        for p in missing_api:
            if p["name"] == "openai":
                console.print("  [cyan]export OPENAI_API_KEY=sk-...[/cyan]")
            elif p["name"] == "anthropic":
                console.print("  [cyan]export ANTHROPIC_API_KEY=sk-ant-...[/cyan]")
