"""Report command for mrbench.

Generates summary report for a benchmark run.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Annotated, TypedDict

import typer
from rich.console import Console

from mrbench.cli._output import emit_json
from mrbench.core.storage import Run, Storage

console = Console()


class ProviderJob(TypedDict):
    """Serialized job details used for report rendering."""

    id: str
    model: str
    status: str
    error: str | None
    metrics: dict[str, float]


class LatencyStats(TypedDict):
    """Latency rollup for a provider."""

    avg: float
    min: float
    max: float
    p95: float


class TokenUsageStats(TypedDict):
    """Token usage rollup for a provider."""

    input_tokens: float
    output_tokens: float
    total_tokens: float


class ProviderStats(TypedDict):
    """Aggregate metrics for a single provider."""

    total_jobs: int
    completed: int
    failed: int
    avg_wall_time_ms: float
    min_wall_time_ms: float
    max_wall_time_ms: float
    avg_ttft_ms: float | None
    latency_ms: LatencyStats
    token_usage: TokenUsageStats
    error_rate: float
    fallback_rate: float


def _percentile(values: list[float], pct: float) -> float:
    """Calculate nearest-rank percentile."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank = max(1, math.ceil((pct / 100) * len(sorted_values))) - 1
    rank = min(rank, len(sorted_values) - 1)
    return sorted_values[rank]


def _get_total_tokens(provider_job: ProviderJob) -> float | None:
    metrics = provider_job["metrics"]
    if "total_tokens" in metrics:
        return metrics["total_tokens"]
    has_partial_tokens = "input_tokens" in metrics or "output_tokens" in metrics
    if not has_partial_tokens:
        return None
    return metrics.get("input_tokens", 0.0) + metrics.get("output_tokens", 0.0)


def _build_provider_stats(providers: dict[str, list[ProviderJob]]) -> dict[str, ProviderStats]:
    stats: dict[str, ProviderStats] = {}

    for provider, pjobs in providers.items():
        completed_jobs = [job for job in pjobs if job["status"] == "completed"]
        failed_jobs = [job for job in pjobs if job["status"] == "failed"]

        wall_times = [
            provider_job["metrics"].get("wall_time_ms", 0.0)
            for provider_job in completed_jobs
            if "wall_time_ms" in provider_job["metrics"]
        ]
        ttfts = [
            provider_job["metrics"]["ttft_ms"]
            for provider_job in completed_jobs
            if "ttft_ms" in provider_job["metrics"]
        ]

        input_tokens = sum(
            provider_job["metrics"].get("input_tokens", 0.0) for provider_job in completed_jobs
        )
        output_tokens = sum(
            provider_job["metrics"].get("output_tokens", 0.0) for provider_job in completed_jobs
        )
        explicit_total_tokens = sum(
            provider_job["metrics"].get("total_tokens", 0.0)
            for provider_job in completed_jobs
            if "total_tokens" in provider_job["metrics"]
        )
        total_tokens = (
            explicit_total_tokens if explicit_total_tokens > 0 else input_tokens + output_tokens
        )

        total_jobs = len(pjobs)
        failed_count = len(failed_jobs)
        fallback_count = sum(
            1 for provider_job in pjobs if provider_job["metrics"].get("fallback_used", 0.0) > 0
        )
        error_rate = (failed_count / total_jobs) if total_jobs else 0.0
        fallback_rate = (fallback_count / total_jobs) if total_jobs else 0.0

        avg_wall = sum(wall_times) / len(wall_times) if wall_times else 0.0
        min_wall = min(wall_times) if wall_times else 0.0
        max_wall = max(wall_times) if wall_times else 0.0

        stats[provider] = {
            "total_jobs": total_jobs,
            "completed": len(completed_jobs),
            "failed": failed_count,
            "avg_wall_time_ms": avg_wall,
            "min_wall_time_ms": min_wall,
            "max_wall_time_ms": max_wall,
            "avg_ttft_ms": sum(ttfts) / len(ttfts) if ttfts else None,
            "latency_ms": {
                "avg": avg_wall,
                "min": min_wall,
                "max": max_wall,
                "p95": _percentile(wall_times, 95),
            },
            "token_usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            "error_rate": error_rate,
            "fallback_rate": fallback_rate,
        }

    return stats


def _render_standard_markdown(
    run_id: str,
    run: Run,
    providers: dict[str, list[ProviderJob]],
    stats: dict[str, ProviderStats],
) -> str:
    lines = [
        f"# Benchmark Report: {run_id[:8]}",
        "",
        f"**Status:** {run.status}",
        f"**Suite:** {run.suite_path or 'N/A'}",
        f"**Created:** {run.created_at}",
        f"**Completed:** {run.completed_at or 'N/A'}",
        "",
        "## Summary",
        "",
        "| Provider | Jobs | Passed | Failed | Latency Avg (ms) | Tokens (total) | Error Rate | Fallback Rate |",
        "|----------|------|--------|--------|------------------|----------------|------------|---------------|",
    ]

    for provider, pstats in stats.items():
        lines.append(
            f"| {provider} | {pstats['total_jobs']} | {pstats['completed']} | "
            f"{pstats['failed']} | {pstats['latency_ms']['avg']:.1f} | "
            f"{pstats['token_usage']['total_tokens']:.0f} | {pstats['error_rate']:.1%} | "
            f"{pstats['fallback_rate']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## Details by Provider",
            "",
        ]
    )

    for provider, pjobs in providers.items():
        lines.extend(
            [
                f"### {provider}",
                "",
            ]
        )

        for provider_job in pjobs:
            status_icon = "✓" if provider_job["status"] == "completed" else "✗"
            wall_time = provider_job["metrics"].get("wall_time_ms", 0.0)
            fallback_used = provider_job["metrics"].get("fallback_used", 0.0) > 0
            total_tokens = _get_total_tokens(provider_job)
            token_text = f"{total_tokens:.0f}" if total_tokens is not None else "n/a"
            lines.append(
                f"- {status_icon} {provider_job['model']}: {wall_time:.1f}ms, "
                f"tokens={token_text}, fallback={'yes' if fallback_used else 'no'}"
            )
            if provider_job["error"]:
                lines.append(f"  - Error: {provider_job['error'][:160]}")

        lines.append("")

    lines.extend(
        [
            "---",
            "*Generated by mrbench*",
        ]
    )

    return "\n".join(lines)


def _render_aws_support_markdown(
    run_id: str,
    run: Run,
    providers: dict[str, list[ProviderJob]],
    stats: dict[str, ProviderStats],
) -> str:
    lines = [
        "# AWS Support Case Attachment",
        "",
        "This report captures hobbyist-scale Anthropic benchmark evidence.",
        "It is intended for practical quota request context and does not claim enterprise throughput.",
        "",
        "## Run Metadata",
        "",
        f"- Run ID: `{run_id}`",
        f"- Suite: `{run.suite_path or 'N/A'}`",
        f"- Status: `{run.status}`",
        f"- Created (UTC): `{run.created_at}`",
        f"- Completed (UTC): `{run.completed_at or 'N/A'}`",
        "",
        "## Provider Summary",
        "",
        "| Provider | Jobs | Latency Avg (ms) | Latency P95 (ms) | Tokens (total) | Error Rate | Fallback Rate |",
        "|----------|------|------------------|------------------|----------------|------------|---------------|",
    ]

    for provider, pstats in stats.items():
        lines.append(
            f"| {provider} | {pstats['total_jobs']} | {pstats['latency_ms']['avg']:.1f} | "
            f"{pstats['latency_ms']['p95']:.1f} | {pstats['token_usage']['total_tokens']:.0f} | "
            f"{pstats['error_rate']:.1%} | {pstats['fallback_rate']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## Job Outcomes",
            "",
            "| Job ID | Provider | Model | Status | Latency (ms) | Tokens | Fallback | Error |",
            "|--------|----------|-------|--------|--------------|--------|----------|-------|",
        ]
    )

    for provider, pjobs in providers.items():
        for provider_job in pjobs:
            wall_time = provider_job["metrics"].get("wall_time_ms", 0.0)
            total_tokens = _get_total_tokens(provider_job)
            fallback_used = provider_job["metrics"].get("fallback_used", 0.0) > 0
            error = (provider_job["error"] or "").replace("\n", " ")
            if len(error) > 80:
                error = f"{error[:77]}..."
            lines.append(
                f"| {provider_job['id'][:8]} | {provider} | {provider_job['model']} | "
                f"{provider_job['status']} | {wall_time:.1f} | "
                f"{(f'{total_tokens:.0f}' if total_tokens is not None else 'n/a')} | "
                f"{'yes' if fallback_used else 'no'} | {error or '-'} |"
            )

    lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- Use this attachment to show observed latency and token demand by workload depth.",
            "- `fallback_rate` > 0 indicates the primary model path was not consistently sufficient.",
            "- Keep quota requests aligned to this hobbyist profile (summary/reasoning/evaluation), not enterprise-scale claims.",
            "",
            "---",
            "*Generated by mrbench*",
        ]
    )

    return "\n".join(lines)


def report_command(
    run_id: Annotated[
        str,
        typer.Argument(help="Run ID to generate report for"),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", "-o", help="Output directory"),
    ] = Path("./out"),
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format (markdown, aws-support-markdown, json)",
        ),
    ] = "markdown",
) -> None:
    """Generate summary report for a benchmark run."""
    with Storage() as storage:
        # Get run
        run = storage.get_run(run_id)
        if run is None:
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)

        # Get jobs
        jobs = storage.get_jobs_for_run(run_id)

        if not jobs:
            console.print("[yellow]No jobs found for this run[/yellow]")
            raise typer.Exit(1)

        # Collect metrics
        job_metrics: dict[str, dict[str, float]] = {}
        for run_job in jobs:
            metrics = storage.get_job_metrics(run_job.id)
            job_metrics[run_job.id] = {m.metric_name: m.metric_value for m in metrics}

        # Group by provider
        providers: dict[str, list[ProviderJob]] = {}
        for run_job in jobs:
            if run_job.provider not in providers:
                providers[run_job.provider] = []

            job_data: ProviderJob = {
                "id": run_job.id,
                "model": run_job.model,
                "status": run_job.status,
                "error": run_job.error_message,
                "metrics": job_metrics.get(run_job.id, {}),
            }
            providers[run_job.provider].append(job_data)

    # Calculate stats per provider
    stats = _build_provider_stats(providers)
    run_dir = output_dir / run_id

    if format == "json":
        report_data = {
            "run_id": run_id,
            "status": run.status,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
            "suite": run.suite_path,
            "providers": stats,
        }
        emit_json(report_data)
        return

    if format == "aws-support-markdown":
        report_content = _render_aws_support_markdown(
            run_id=run_id,
            run=run,
            providers=providers,
            stats=stats,
        )
        report_filename = "report_aws_support.md"
    else:
        report_content = _render_standard_markdown(
            run_id=run_id,
            run=run,
            providers=providers,
            stats=stats,
        )
        report_filename = "report.md"

    # Write report
    if run_dir.exists():
        report_file = run_dir / report_filename
        report_file.write_text(report_content)
        console.print(f"[green]✓ Report written to {report_file}[/green]")
    else:
        # Just print to console
        console.print(report_content)
