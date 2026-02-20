"""Run command for mrbench.

Runs a single prompt against a provider.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from mrbench.adapters.base import RunOptions
from mrbench.adapters.registry import get_default_registry
from mrbench.cli._output import emit_json
from mrbench.core.redaction import redact_secrets

console = Console()


def run_command(
    provider: Annotated[
        str,
        typer.Option(
            "--provider",
            "-p",
            help="Provider name (e.g., 'ollama', 'openai', 'anthropic')",
        ),
    ],
    model: Annotated[
        str,
        typer.Option("--model", "-m", help="Model name (e.g., 'llama3.2', 'gpt-4o-mini')"),
    ],
    prompt: Annotated[
        str,
        typer.Option("--prompt", help="Prompt file path or '-' for stdin"),
    ],
    stream: Annotated[
        bool,
        typer.Option("--stream", "-s", help="Stream output as it arrives"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output result as JSON"),
    ] = False,
    timeout: Annotated[
        float,
        typer.Option("--timeout", "-t", help="Timeout in seconds"),
    ] = 300.0,
) -> None:
    """Run a single prompt against a provider.

    Examples:
        mrbench run --provider ollama --model llama3.2 --prompt "Hello"
        mrbench run --provider openai --model gpt-4o-mini --prompt - < input.txt
        mrbench run --provider anthropic --model claude-3-haiku --prompt "Hi" --json
    """
    registry = get_default_registry()

    # Get adapter
    adapter = registry.get(provider)
    if adapter is None:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        console.print(f"Available: {', '.join(registry.list_names())}")
        raise typer.Exit(1)

    # Check availability with helpful error messages
    if not adapter.is_available():
        if provider == "openai":
            console.print(f"[yellow]Provider '{provider}' is not available.[/yellow]")
            console.print("Install API support: [cyan]pip install mrbench[api][/cyan]")
            console.print("Set your API key: [cyan]export OPENAI_API_KEY=sk-...[/cyan]")
        elif provider == "anthropic":
            console.print(f"[yellow]Provider '{provider}' is not available.[/yellow]")
            console.print("Install API support: [cyan]pip install mrbench[api][/cyan]")
            console.print("Set your API key: [cyan]export ANTHROPIC_API_KEY=sk-ant-...[/cyan]")
        else:
            console.print(f"[yellow]Provider '{provider}' is not available.[/yellow]")
            console.print("Run 'mrbench doctor' for details.")
        raise typer.Exit(1)

    # Read prompt
    if prompt == "-":
        prompt_text = sys.stdin.read()
    else:
        prompt_path = Path(prompt)
        if not prompt_path.exists():
            console.print(f"[red]Prompt file not found: {prompt}[/red]")
            raise typer.Exit(1)
        prompt_text = prompt_path.read_text()

    if not prompt_text.strip():
        console.print("[red]Empty prompt[/red]")
        raise typer.Exit(1)

    # Build options
    def stream_callback(chunk: str) -> None:
        if not json_output:
            console.print(chunk, end="")

    options = RunOptions(
        model=model,
        stream=stream,
        timeout=timeout,
        stream_callback=stream_callback if stream else None,
    )

    # Run
    try:
        result = adapter.run(prompt_text, options)
    except Exception as e:
        console.print(f"[red]Error running prompt: {e}[/red]")
        raise typer.Exit(1) from None

    if json_output:
        output_data = {
            "provider": provider,
            "model": model,
            "exit_code": result.exit_code,
            "wall_time_ms": result.wall_time_ms,
            "ttft_ms": result.ttft_ms,
            "output": result.output,
            "error": redact_secrets(result.error) if result.error else None,
            "token_count_input": result.token_count_input,
            "token_count_output": result.token_count_output,
            "tokens_estimated": result.tokens_estimated,
        }
        emit_json(output_data)
    else:
        if not stream and result.output:
            # Print output if not streaming (streaming already printed).
            console.print(result.output)
        if result.exit_code != 0 and result.error:
            console.print(f"[red]{redact_secrets(result.error)}[/red]")

    if result.exit_code != 0:
        raise typer.Exit(result.exit_code)
