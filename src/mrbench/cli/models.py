"""Models command for mrbench.

Lists available models for a provider.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from mrbench.adapters.registry import get_default_registry

console = Console()


def models_command(
    provider: Annotated[
        str | None,
        typer.Argument(help="Provider name (e.g., 'ollama')"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """List available models for a provider."""
    registry = get_default_registry()

    if provider is None:
        # List models for all detected providers
        all_models: dict[str, list[str]] = {}

        for adapter in registry.get_available():
            try:
                models = adapter.list_models()
                if models:
                    all_models[adapter.name] = models
            except Exception:
                pass

        if json_output:
            console.print(json.dumps(all_models, indent=2))
            return

        if not all_models:
            console.print("[yellow]No models found. Ensure providers are running.[/yellow]")
            return

        for pname, models in all_models.items():
            console.print(f"\n[bold cyan]{pname}[/bold cyan]")
            for model in models:
                console.print(f"  • {model}")
        console.print()
        return

    # Specific provider
    selected_adapter = registry.get(provider)
    if selected_adapter is None:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        raise typer.Exit(1)

    if not selected_adapter.is_available():
        console.print(f"[yellow]Provider '{provider}' is not available.[/yellow]")
        raise typer.Exit(1)

    try:
        models = selected_adapter.list_models()
    except Exception as e:
        console.print(f"[red]Error listing models: {e}[/red]")
        raise typer.Exit(1) from None

    if json_output:
        console.print(json.dumps(models, indent=2))
        return

    if not models:
        console.print(f"[yellow]No models available for {provider}.[/yellow]")
        console.print("[dim]You may need to specify a model ID manually.[/dim]")
        return

    table = Table(title=f"Models for {provider}", show_header=True)
    table.add_column("Model", style="cyan")

    for model in models:
        table.add_row(model)

    console.print(table)
