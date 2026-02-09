"""Bench command for mrbench.

Runs benchmark suite across providers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from mrbench.adapters.base import RunOptions
from mrbench.adapters.registry import get_default_registry
from mrbench.core.storage import Storage, hash_prompt

console = Console()


def bench_command(
    suite: Annotated[
        Path,
        typer.Option("--suite", "-s", help="Path to benchmark suite YAML"),
    ],
    provider: Annotated[
        str | None,
        typer.Option("--provider", "-p", help="Limit to specific provider"),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Output directory"),
    ] = Path("./out"),
    json_output: Annotated[
        bool,
        typer.Option("--json", "-j", help="Output as JSON"),
    ] = False,
    store_prompts: Annotated[
        bool,
        typer.Option("--store-prompts", help="Store full prompts in output"),
    ] = False,
) -> None:
    """Run benchmark suite across providers."""
    if not suite.exists():
        console.print(f"[red]Suite file not found: {suite}[/red]")
        raise typer.Exit(1)

    # Load suite
    with open(suite) as f:
        suite_data = yaml.safe_load(f)

    suite_name = suite_data.get("name", suite.stem)
    prompts = suite_data.get("prompts", [])

    if not prompts:
        console.print("[red]No prompts in suite[/red]")
        raise typer.Exit(1)

    registry = get_default_registry()

    # Get providers to test
    if provider:
        adapter = registry.get(provider)
        if adapter is None or not adapter.is_available():
            console.print(f"[red]Provider not available: {provider}[/red]")
            raise typer.Exit(1)
        adapters = [adapter]
    else:
        adapters = registry.get_available()

    if not adapters:
        console.print("[red]No providers available[/red]")
        raise typer.Exit(1)

    with Storage() as storage:
        run = storage.create_run(suite_path=str(suite))

        # Create output directory
        run_dir = output_dir / run.id
        jobs_dir = run_dir / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, Any] = {
            "run_id": run.id,
            "suite": suite_name,
            "started_at": datetime.now(UTC).isoformat(),
            "providers": [],
            "jobs": [],
        }

        total_jobs = len(prompts) * len(adapters)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            disable=json_output,
        ) as progress:
            task = progress.add_task(f"Running {total_jobs} jobs...", total=total_jobs)

            for adapter in adapters:
                adapter.get_capabilities()

                # Get default model
                models = adapter.list_models()
                model = models[0] if models else "default"

                for prompt_data in prompts:
                    prompt_id = prompt_data.get("id", "unknown")
                    prompt_text = prompt_data.get("text", "")

                    progress.update(
                        task,
                        description=f"[{adapter.name}] {prompt_id}",
                    )

                    # Create job in storage
                    job = storage.create_job(
                        run_id=run.id,
                        provider=adapter.name,
                        model=model,
                        prompt_hash=hash_prompt(prompt_text),
                        prompt_preview=prompt_text[:100] if prompt_text else None,
                    )

                    storage.start_job(job.id)

                    # Run the prompt
                    options = RunOptions(model=model)

                    try:
                        result = adapter.run(prompt_text, options)

                        storage.complete_job(
                            job.id,
                            exit_code=result.exit_code,
                            error_message=result.error,
                        )

                        # Add metrics
                        storage.add_metric(job.id, "wall_time_ms", result.wall_time_ms, "ms")
                        if result.ttft_ms is not None:
                            storage.add_metric(job.id, "ttft_ms", result.ttft_ms, "ms")
                        if result.token_count_output is not None:
                            storage.add_metric(
                                job.id,
                                "output_tokens",
                                result.token_count_output,
                                "tokens",
                                is_estimated=result.tokens_estimated,
                            )

                        # Write job output
                        job_file = jobs_dir / f"{job.id}.json"
                        job_data = {
                            "job_id": job.id,
                            "prompt_id": prompt_id,
                            "provider": adapter.name,
                            "model": model,
                            "exit_code": result.exit_code,
                            "wall_time_ms": result.wall_time_ms,
                            "ttft_ms": result.ttft_ms,
                            "output_length": len(result.output),
                            "error": result.error,
                        }
                        with open(job_file, "w") as f:
                            json.dump(job_data, f, indent=2)

                        # Store prompt if requested
                        if store_prompts:
                            prompt_file = jobs_dir / f"{job.id}.prompt.txt"
                            prompt_file.write_text(prompt_text)

                        # Store output
                        output_file = jobs_dir / f"{job.id}.output.txt"
                        output_file.write_text(result.output)

                        results["jobs"].append(job_data)

                    except Exception as e:
                        storage.complete_job(job.id, exit_code=1, error_message=str(e))
                        results["jobs"].append(
                            {
                                "job_id": job.id,
                                "prompt_id": prompt_id,
                                "provider": adapter.name,
                                "model": model,
                                "error": str(e),
                            }
                        )

                    progress.advance(task)

        # Complete run
        storage.complete_run(run.id)
        results["completed_at"] = datetime.now(UTC).isoformat()

    # Write run metadata
    meta_file = run_dir / "run_meta.json"
    with open(meta_file, "w") as f:
        json.dump(results, f, indent=2)

    if json_output:
        console.print(json.dumps({"run_id": run.id, "output_dir": str(run_dir)}, indent=2))
    else:
        console.print(f"\n[green]✓ Completed benchmark run: {run.id}[/green]")
        console.print(f"[dim]Output: {run_dir}[/dim]")
        console.print(f"\nGenerate report with: [cyan]mrbench report {run.id}[/cyan]")
