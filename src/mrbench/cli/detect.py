"""Detect command for mrbench.

Runs discovery and records capability snapshot.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from mrbench.adapters.registry import get_default_registry
from mrbench.core.config import get_default_data_path

console = Console()


def detect_command(
    write: Annotated[
        bool,
        typer.Option("--write", "-w", help="Write capabilities to cache file"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Output directory for cache file"),
    ] = None,
) -> None:
    """Run discovery and record capability snapshot."""
    registry = get_default_registry()

    results: dict[str, Any] = {
        "detected_at": datetime.now(UTC).isoformat(),
        "providers": [],
    }

    for adapter in registry.list_all():
        detection = adapter.detect()

        if not detection.detected:
            continue

        # Get models if possible
        try:
            models = adapter.list_models()
        except Exception:
            models = []

        # Get capabilities
        capabilities = adapter.get_capabilities()

        provider_info: dict[str, Any] = {
            "name": adapter.name,
            "display_name": adapter.display_name,
            "binary_path": detection.binary_path,
            "version": detection.version,
            "auth_status": detection.auth_status,
            "trusted": detection.trusted,
            "models": models,
            "capabilities": {
                "streaming": capabilities.streaming,
                "tool_calling": capabilities.tool_calling,
                "max_tokens": capabilities.max_tokens,
                "max_context": capabilities.max_context,
                "offline": capabilities.offline,
            },
        }

        results["providers"].append(provider_info)

    if write:
        cache_dir = output_dir or get_default_data_path() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "capabilities.json"

        with open(cache_file, "w") as f:
            json.dump(results, f, indent=2)

        if not json_output:
            console.print(f"[green]✓ Wrote capabilities to {cache_file}[/green]")

    if json_output:
        console.print(json.dumps(results, indent=2))
    elif not write:
        # Pretty print summary
        console.print(f"\n[bold]Detected {len(results['providers'])} providers:[/bold]\n")
        for provider in results["providers"]:
            models_count = len(provider.get("models", []))
            models_str = f"{models_count} models" if models_count else "no model list"
            console.print(f"  • [cyan]{provider['display_name']}[/cyan] ({models_str})")
        console.print()
