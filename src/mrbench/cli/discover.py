"""Discover command for mrbench.

Discovers all AI CLI tools and their configurations on the system.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mrbench.core.discovery import ConfigDetector

console = Console()


def discover_command(
    all_tools: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show all known tools, including not found"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
    check_auth: Annotated[
        bool,
        typer.Option("--check-auth", "-c", help="Run auth check commands"),
    ] = False,
) -> None:
    """Discover AI CLI tools and configurations on the system.

    Scans for installed AI/coding CLI tools and checks their configuration
    status, including config files and authentication.
    """
    detector = ConfigDetector()
    results = detector.discover_cli_tools()

    if json_output:
        console.print(json.dumps(results, indent=2))
        return

    # Rich output
    console.print()
    console.print("[bold blue]AI CLI Tool Discovery[/bold blue]")
    console.print()

    # Summary
    installed_count = len(results["installed"])
    configured_count = len(results["configured"])
    ready_count = len(results["ready"])

    console.print(f"[bold]Installed:[/bold] {installed_count} tools")
    console.print(f"[bold]Configured:[/bold] {configured_count} tools")
    console.print(f"[bold]Ready:[/bold] {ready_count} tools")
    console.print()

    # Installed tools table
    if results["installed"]:
        table = Table(title="Installed AI CLI Tools", show_header=True, header_style="bold cyan")
        table.add_column("Tool", style="cyan")
        table.add_column("Status")
        table.add_column("Config")
        table.add_column("Path")

        for tool in results["installed"]:
            name = tool["name"]
            has_config = tool["has_config"]

            # Check if ready
            is_ready = any(r["name"] == name for r in results["ready"])

            if is_ready:
                status = "[green]✓ Ready[/green]"
            elif has_config:
                status = "[yellow]◐ Configured[/yellow]"
            else:
                status = "[dim]○ Installed[/dim]"

            config = tool["config_path"] if has_config else "[dim]none[/dim]"
            if has_config and len(config) > 35:
                config = "..." + config[-32:]

            path = tool["path"]
            if len(path) > 35:
                path = "..." + path[-32:]

            table.add_row(name, status, config, path)

        console.print(table)
        console.print()

    # Not found tools (if --all)
    if all_tools and results["not_found"]:
        console.print("[dim]Not installed:[/dim]")
        for tool in sorted(results["not_found"]):
            console.print(f"  [dim]• {tool}[/dim]")
        console.print()

    # Check auth for specific providers if requested
    if check_auth and results["installed"]:
        console.print("[bold]Auth Check Results:[/bold]")
        console.print()

        for tool in results["installed"]:
            result = detector.check_provider(tool["name"])
            if result.has_binary:
                if result.auth_status == "authenticated":
                    console.print(f"  [green]✓[/green] {tool['name']}: authenticated")
                elif result.auth_status == "not_authenticated":
                    console.print(f"  [yellow]○[/yellow] {tool['name']}: not authenticated")
                elif result.auth_status == "error":
                    err = result.errors[0] if result.errors else "unknown error"
                    console.print(f"  [red]✗[/red] {tool['name']}: {err}")
                else:
                    console.print(f"  [dim]?[/dim] {tool['name']}: {result.auth_status}")

        console.print()
