"""Route command for mrbench.

Chooses best provider based on constraints.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from mrbench.adapters.registry import get_default_registry
from mrbench.cli._output import emit_json
from mrbench.core.config import load_config

console = Console()


def route_command(
    prompt: Annotated[
        str,
        typer.Option("--prompt", help="Prompt file path or '-' for stdin"),
    ],
    explain: Annotated[
        bool,
        typer.Option("--explain", "-e", help="Show routing explanation"),
    ] = False,
    offline_only: Annotated[
        bool,
        typer.Option("--offline-only", help="Only consider offline/local providers"),
    ] = False,
    streaming_required: Annotated[
        bool,
        typer.Option("--streaming-required", help="Only providers that support streaming"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
) -> None:
    """Choose best provider based on constraints."""
    registry = get_default_registry()
    config = load_config()

    # Read prompt (just to validate, not used for routing in MVP)
    if prompt == "-":
        prompt_text = sys.stdin.read()
    else:
        prompt_path = Path(prompt)
        if not prompt_path.exists():
            console.print(f"[red]Prompt file not found: {prompt}[/red]")
            raise typer.Exit(1)
        prompt_text = prompt_path.read_text()

    _ = prompt_text  # Unused in MVP routing, but validated

    # Get available adapters
    available = registry.get_available()

    if not available:
        console.print("[red]No providers available.[/red]")
        raise typer.Exit(1)

    # Filter by constraints
    candidates: list[tuple[Any, list[str]]] = []

    for adapter in available:
        caps = adapter.get_capabilities()
        reasons: list[str] = []

        # Check offline constraint
        if offline_only and not caps.offline:
            reasons.append("requires network (offline_only constraint)")
            continue

        # Check streaming constraint
        if streaming_required and not caps.streaming:
            reasons.append("no streaming support")
            continue

        candidates.append((adapter, reasons))

    if not candidates:
        console.print("[red]No providers match the constraints.[/red]")
        raise typer.Exit(1)

    # Sort by preference order from config
    preference_order = config.routing.preference_order

    def sort_key(item: tuple[Any, list[str]]) -> int:
        adapter, _ = item
        try:
            return preference_order.index(adapter.name)
        except ValueError:
            return len(preference_order)  # Unknown providers go last

    candidates.sort(key=sort_key)

    # Select first candidate
    selected, _ = candidates[0]
    caps = selected.get_capabilities()

    # Get default model for provider
    provider_config = config.providers.get(selected.name)
    default_model = provider_config.default_model if provider_config else None

    if not default_model:
        # Try to get first model from list
        models = selected.list_models()
        default_model = models[0] if models else "default"

    result: dict[str, Any] = {
        "provider": selected.name,
        "model": default_model,
        "offline": caps.offline,
        "streaming": caps.streaming,
    }

    if explain:
        reasons = []
        reasons.append(f"Provider '{selected.name}' is available")

        pref_idx = (
            preference_order.index(selected.name) if selected.name in preference_order else -1
        )
        if pref_idx >= 0:
            reasons.append(f"Ranked #{pref_idx + 1} in preference order")

        if offline_only:
            reasons.append("Matches offline_only constraint")

        if streaming_required:
            reasons.append("Supports streaming")

        result["explanation"] = reasons

    if json_output:
        emit_json(result)
    else:
        console.print(f"[bold]Provider:[/bold] [cyan]{result['provider']}[/cyan]")
        console.print(f"[bold]Model:[/bold] {result['model']}")

        if explain:
            console.print("\n[bold]Reasoning:[/bold]")
            for reason in result.get("explanation", []):
                console.print(f"  • {reason}")
