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

from mrbench.adapters.base import RunOptions, RunResult
from mrbench.adapters.registry import get_default_registry
from mrbench.cli._output import emit_json
from mrbench.core.redaction import redact_for_storage
from mrbench.core.storage import Storage, hash_prompt

console = Console()


def _normalize_model_list(raw_models: Any) -> list[str]:
    """Normalize model lists from suite YAML fields."""
    if isinstance(raw_models, str):
        stripped = raw_models.strip()
        return [stripped] if stripped else []
    if not isinstance(raw_models, list):
        return []
    models: list[str] = []
    for candidate in raw_models:
        if isinstance(candidate, str):
            stripped = candidate.strip()
            if stripped:
                models.append(stripped)
    return models


def _resolve_models_for_prompt(
    prompt_data: dict[str, Any],
    provider_name: str,
    default_model: str,
) -> tuple[str, list[str]]:
    """Resolve primary and fallback models for a provider on a prompt."""
    primary_model = default_model

    model_overrides = prompt_data.get("model_overrides")
    if isinstance(model_overrides, dict):
        override = model_overrides.get(provider_name)
        if isinstance(override, str) and override.strip():
            primary_model = override.strip()

    fallback_models: list[str] = []
    raw_fallbacks = prompt_data.get("fallback_models")
    if isinstance(raw_fallbacks, dict):
        fallback_models = _normalize_model_list(raw_fallbacks.get(provider_name))

    # Keep only unique fallback models different from primary.
    unique_fallbacks: list[str] = []
    for fallback_model in fallback_models:
        if fallback_model != primary_model and fallback_model not in unique_fallbacks:
            unique_fallbacks.append(fallback_model)

    return primary_model, unique_fallbacks


def _run_prompt_with_fallback(
    adapter: Any,
    prompt_text: str,
    candidate_models: list[str],
) -> tuple[RunResult, str, bool]:
    """Run a prompt, falling back to additional models after failures."""
    failures: list[str] = []
    last_result: RunResult | None = None
    final_model = candidate_models[0]
    fallback_used = False

    for idx, model_name in enumerate(candidate_models):
        options = RunOptions(model=model_name)
        final_model = model_name
        fallback_used = idx > 0

        try:
            result = adapter.run(prompt_text, options)
        except Exception as exc:
            failures.append(f"{model_name}: {exc}")
            if idx == len(candidate_models) - 1:
                return (
                    RunResult(
                        output="",
                        exit_code=1,
                        wall_time_ms=0,
                        error="; ".join(failures),
                    ),
                    final_model,
                    fallback_used,
                )
            continue

        last_result = result
        if result.exit_code == 0:
            return result, final_model, fallback_used

        failure_reason = result.error or f"exit_code={result.exit_code}"
        failures.append(f"{model_name}: {failure_reason}")

    if last_result is None:
        return (
            RunResult(
                output="",
                exit_code=1,
                wall_time_ms=0,
                error="No model attempts were executed",
            ),
            final_model,
            fallback_used,
        )

    if failures:
        attempts_summary = "; ".join(failures)
        if last_result.error:
            last_result.error = f"{last_result.error} | attempts: {attempts_summary}"
        else:
            last_result.error = f"attempts: {attempts_summary}"

    return last_result, final_model, fallback_used


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

    if not isinstance(suite_data, dict):
        console.print("[red]Invalid suite format: expected mapping at document root[/red]")
        raise typer.Exit(1)

    raw_suite_name = suite_data.get("name", suite.stem)
    suite_name = (
        raw_suite_name if isinstance(raw_suite_name, str) and raw_suite_name else suite.stem
    )
    prompts_raw = suite_data.get("prompts")

    if not isinstance(prompts_raw, list) or not prompts_raw:
        console.print("[red]No prompts in suite[/red]")
        raise typer.Exit(1)

    prompts: list[dict[str, Any]] = []
    for idx, prompt_entry in enumerate(prompts_raw):
        if not isinstance(prompt_entry, dict):
            console.print(f"[red]Invalid prompt entry at index {idx}[/red]")
            raise typer.Exit(1)

        prompt_text = prompt_entry.get("text")
        if not isinstance(prompt_text, str) or not prompt_text.strip():
            console.print(f"[red]Prompt text cannot be empty (index {idx})[/red]")
            raise typer.Exit(1)

        prompts.append(prompt_entry)

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
                default_model = models[0] if models else "default"

                for prompt_data in prompts:
                    prompt_id = prompt_data.get("id", "unknown")
                    prompt_text = prompt_data.get("text", "")
                    primary_model, fallback_models = _resolve_models_for_prompt(
                        prompt_data=prompt_data,
                        provider_name=adapter.name,
                        default_model=default_model,
                    )
                    candidate_models = [primary_model, *fallback_models]

                    progress.update(
                        task,
                        description=f"[{adapter.name}] {prompt_id}",
                    )

                    # Create job in storage
                    job = storage.create_job(
                        run_id=run.id,
                        provider=adapter.name,
                        model=primary_model,
                        prompt_hash=hash_prompt(prompt_text),
                        prompt_preview=(
                            redact_for_storage(prompt_text[:100]) if store_prompts else None
                        ),
                    )

                    storage.start_job(job.id)

                    result, resolved_model, fallback_used = _run_prompt_with_fallback(
                        adapter=adapter,
                        prompt_text=prompt_text,
                        candidate_models=candidate_models,
                    )

                    if resolved_model != primary_model:
                        storage.set_job_model(job.id, resolved_model)

                    storage.complete_job(
                        job.id,
                        exit_code=result.exit_code,
                        error_message=result.error,
                    )

                    # Add metrics
                    storage.add_metric(job.id, "wall_time_ms", result.wall_time_ms, "ms")
                    if result.ttft_ms is not None:
                        storage.add_metric(job.id, "ttft_ms", result.ttft_ms, "ms")
                    if result.token_count_input is not None:
                        storage.add_metric(
                            job.id,
                            "input_tokens",
                            result.token_count_input,
                            "tokens",
                            is_estimated=result.tokens_estimated,
                        )
                    if result.token_count_output is not None:
                        storage.add_metric(
                            job.id,
                            "output_tokens",
                            result.token_count_output,
                            "tokens",
                            is_estimated=result.tokens_estimated,
                        )
                    if result.token_count_input is not None or result.token_count_output is not None:
                        input_tokens = result.token_count_input or 0
                        output_tokens = result.token_count_output or 0
                        storage.add_metric(
                            job.id,
                            "total_tokens",
                            input_tokens + output_tokens,
                            "tokens",
                            is_estimated=result.tokens_estimated,
                        )
                    storage.add_metric(
                        job.id,
                        "fallback_used",
                        1.0 if fallback_used else 0.0,
                        "ratio",
                    )

                    # Write job output
                    job_file = jobs_dir / f"{job.id}.json"
                    job_data = {
                        "job_id": job.id,
                        "prompt_id": prompt_id,
                        "provider": adapter.name,
                        "model": resolved_model,
                        "primary_model": primary_model,
                        "fallback_models": fallback_models,
                        "fallback_used": fallback_used,
                        "exit_code": result.exit_code,
                        "wall_time_ms": result.wall_time_ms,
                        "ttft_ms": result.ttft_ms,
                        "input_tokens": result.token_count_input,
                        "output_tokens": result.token_count_output,
                        "total_tokens": (
                            (result.token_count_input or 0) + (result.token_count_output or 0)
                            if result.token_count_input is not None
                            or result.token_count_output is not None
                            else None
                        ),
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

                    progress.advance(task)

        # Complete run
        storage.complete_run(run.id)
        results["completed_at"] = datetime.now(UTC).isoformat()

    # Write run metadata
    meta_file = run_dir / "run_meta.json"
    with open(meta_file, "w") as f:
        json.dump(results, f, indent=2)

    if json_output:
        emit_json({"run_id": run.id, "output_dir": str(run_dir)})
    else:
        console.print(f"\n[green]✓ Completed benchmark run: {run.id}[/green]")
        console.print(f"[dim]Output: {run_dir}[/dim]")
        console.print(f"\nGenerate report with: [cyan]mrbench report {run.id}[/cyan]")
