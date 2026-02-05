"""Main CLI application for mrbench."""

from typing import Annotated

import typer
from rich.console import Console

import mrbench
from mrbench.cli.bench import bench_command
from mrbench.cli.detect import detect_command
from mrbench.cli.doctor import doctor_command
from mrbench.cli.models import models_command
from mrbench.cli.providers import providers_command
from mrbench.cli.report import report_command
from mrbench.cli.route import route_command
from mrbench.cli.run import run_command

console = Console()

app = typer.Typer(
    name="mrbench",
    help="Model Router + Benchmark - Route prompts to AI CLIs and benchmark them.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"mrbench version {mrbench.__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """mrbench - Model Router + Benchmark CLI."""
    pass


# Register commands
app.command(name="doctor", help="Check prerequisites and show detected providers")(doctor_command)
app.command(name="detect", help="Run discovery and record capability snapshot")(detect_command)
app.command(name="providers", help="List detected providers/adapters")(providers_command)
app.command(name="models", help="List available models for a provider")(models_command)
app.command(name="run", help="Run a single prompt against a provider")(run_command)
app.command(name="route", help="Choose best provider based on constraints")(route_command)
app.command(name="bench", help="Run benchmark suite across providers")(bench_command)
app.command(name="report", help="Generate summary report for a run")(report_command)


if __name__ == "__main__":
    app()
