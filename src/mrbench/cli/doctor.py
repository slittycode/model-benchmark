"""Doctor command for mrbench.

Checks system prerequisites and shows detected providers.
"""

from __future__ import annotations

import json
import platform
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mrbench.adapters.registry import get_default_registry

console = Console()


def doctor_command(
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """Check prerequisites and show detected providers."""
    results: dict[str, Any] = {
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "platform_version": platform.release(),
        "providers": [],
    }

    registry = get_default_registry()

    # Check each adapter
    for adapter in registry.list_all():
        detection = adapter.detect()
        provider_info: dict[str, Any] = {
            "name": adapter.name,
            "display_name": adapter.display_name,
            "detected": detection.detected,
        }

        if detection.detected:
            provider_info["binary_path"] = detection.binary_path
            provider_info["version"] = detection.version
            provider_info["auth_status"] = detection.auth_status
            provider_info["trusted"] = detection.trusted
        else:
            provider_info["error"] = detection.error

        results["providers"].append(provider_info)

    if json_output:
        console.print(json.dumps(results, indent=2))
        return

    # Rich output
    console.print()
    console.print(Panel.fit("[bold blue]mrbench doctor[/bold blue]", border_style="blue"))
    console.print()

    # System info
    console.print(f"[bold]Python:[/bold] {results['python_version']}")
    console.print(f"[bold]Platform:[/bold] {results['platform']} {results['platform_version']}")
    console.print()

    # Provider table
    table = Table(title="Provider Status", show_header=True, header_style="bold magenta")
    table.add_column("Provider", style="cyan")
    table.add_column("Status")
    table.add_column("Version")
    table.add_column("Auth")
    table.add_column("Path")

    for provider in results["providers"]:
        if provider["detected"]:
            status = "[green]✓ Detected[/green]"
            version = provider.get("version") or "-"
            auth = provider.get("auth_status") or "unknown"

            if auth == "authenticated":
                auth = "[green]authenticated[/green]"
            elif auth == "unauthenticated":
                auth = "[yellow]unauthenticated[/yellow]"
            else:
                auth = "[dim]unknown[/dim]"

            path = provider.get("binary_path") or "-"
            if len(path) > 30:
                path = "..." + path[-27:]
        else:
            status = "[red]✗ Not found[/red]"
            version = "-"
            auth = "-"
            path = provider.get("error") or "-"

        table.add_row(
            provider["display_name"],
            status,
            version,
            auth,
            path,
        )

    console.print(table)
    console.print()

    # Summary
    detected_count = sum(1 for p in results["providers"] if p["detected"])
    total_count = len(results["providers"])

    if detected_count == 0:
        console.print(
            "[yellow]⚠ No providers detected. Install Ollama or another AI CLI to get started.[/yellow]"
        )
        console.print()
        console.print("[dim]Install suggestions:[/dim]")
        console.print("  • Ollama: https://ollama.com/download")
        console.print("  • Claude Code: npm install -g @anthropic-ai/claude-code")
        console.print("  • Gemini CLI: npm install -g @anthropic-ai/gemini-cli")
    else:
        console.print(f"[green]✓ {detected_count}/{total_count} providers available[/green]")

    console.print()
