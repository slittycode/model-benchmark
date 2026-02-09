"""Report command for mrbench.

Generates summary report for a benchmark run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, TypedDict

import typer
from rich.console import Console

from mrbench.core.storage import Storage

console = Console()


class ProviderJob(TypedDict):
    """Serialized job details used for report rendering."""

    id: str
    model: str
    status: str
    error: str | None
    metrics: dict[str, float]


class ProviderStats(TypedDict):
    """Aggregate metrics for a single provider."""

    total_jobs: int
    completed: int
    failed: int
    avg_wall_time_ms: float
    min_wall_time_ms: float
    max_wall_time_ms: float
    avg_ttft_ms: float | None


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
        typer.Option("--format", "-f", help="Output format (markdown, json)"),
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
        stats: dict[str, ProviderStats] = {}
        for provider, pjobs in providers.items():
            wall_times = [
                j["metrics"].get("wall_time_ms", 0) for j in pjobs if j["status"] == "completed"
            ]
            ttfts = [
                j["metrics"]["ttft_ms"]
                for j in pjobs
                if j["status"] == "completed" and "ttft_ms" in j["metrics"]
            ]

            stats[provider] = {
                "total_jobs": len(pjobs),
                "completed": len([j for j in pjobs if j["status"] == "completed"]),
                "failed": len([j for j in pjobs if j["status"] == "failed"]),
                "avg_wall_time_ms": sum(wall_times) / len(wall_times) if wall_times else 0,
                "min_wall_time_ms": min(wall_times) if wall_times else 0,
                "max_wall_time_ms": max(wall_times) if wall_times else 0,
                "avg_ttft_ms": sum(ttfts) / len(ttfts) if ttfts else None,
            }

    run_dir = output_dir / run_id

    if format == "json":
        report_data = {
            "run_id": run_id,
            "status": run.status,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
            "providers": stats,
        }
        console.print(json.dumps(report_data, indent=2))
        return

    # Generate Markdown
    lines = [
        f"# Benchmark Report: {run_id[:8]}",
        "",
        f"**Status:** {run.status}",
        f"**Created:** {run.created_at}",
        f"**Completed:** {run.completed_at or 'N/A'}",
        "",
        "## Summary",
        "",
        "| Provider | Jobs | Passed | Failed | Avg Time (ms) | Min (ms) | Max (ms) |",
        "|----------|------|--------|--------|---------------|----------|----------|",
    ]

    for provider, pstats in stats.items():
        lines.append(
            f"| {provider} | {pstats['total_jobs']} | {pstats['completed']} | "
            f"{pstats['failed']} | {pstats['avg_wall_time_ms']:.1f} | "
            f"{pstats['min_wall_time_ms']:.1f} | {pstats['max_wall_time_ms']:.1f} |"
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
            wall_time = provider_job["metrics"].get("wall_time_ms", 0)
            lines.append(f"- {status_icon} {provider_job['model']}: {wall_time:.1f}ms")
            if provider_job["error"]:
                lines.append(f"  - Error: {provider_job['error'][:100]}")

        lines.append("")

    lines.extend(
        [
            "---",
            "*Generated by mrbench*",
        ]
    )

    report_content = "\n".join(lines)

    # Write report
    if run_dir.exists():
        report_file = run_dir / "report.md"
        report_file.write_text(report_content)
        console.print(f"[green]✓ Report written to {report_file}[/green]")
    else:
        # Just print to console
        console.print(report_content)
