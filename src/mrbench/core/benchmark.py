"""Benchmark orchestration for mrbench.

Coordinates running benchmark suites across multiple providers.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

if TYPE_CHECKING:
    from mrbench.adapters.base import Adapter
    from mrbench.adapters.registry import AdapterRegistry
    from mrbench.core.storage import Storage


@dataclass
class BenchmarkPrompt:
    """A single prompt in a benchmark suite."""

    id: str
    text: str
    expected: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkSuite:
    """A benchmark suite definition."""

    name: str
    description: str
    prompts: list[BenchmarkPrompt]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> BenchmarkSuite:
        """Load suite from YAML file."""
        with open(path) as f:
            loaded_data = yaml.safe_load(f)

        data = loaded_data if isinstance(loaded_data, dict) else {}

        prompts: list[BenchmarkPrompt] = []
        for p in cast(list[dict[str, Any]], data.get("prompts", [])):
            prompts.append(
                BenchmarkPrompt(
                    id=p.get("id", f"prompt_{len(prompts)}"),
                    text=p.get("text", ""),
                    expected=p.get("expected"),
                    tags=p.get("tags", []),
                    metadata=p.get("metadata", {}),
                )
            )

        return cls(
            name=data.get("name", path.stem),
            description=data.get("description", ""),
            prompts=prompts,
            metadata=data.get("metadata", {}),
        )


@dataclass
class BenchmarkResult:
    """Result of a benchmark job."""

    prompt_id: str
    provider: str
    model: str
    success: bool
    wall_time_ms: float
    ttft_ms: float | None = None
    output: str = ""
    error: str | None = None
    token_count_input: int | None = None
    token_count_output: int | None = None


@dataclass
class BenchmarkRun:
    """A complete benchmark run."""

    run_id: str
    suite_name: str
    results: list[BenchmarkResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None


class BenchmarkOrchestrator:
    """Orchestrates benchmark runs across providers."""

    def __init__(
        self,
        registry: AdapterRegistry,
        storage: Storage,
    ) -> None:
        self._registry = registry
        self._storage = storage

    def run_suite(
        self,
        suite: BenchmarkSuite,
        providers: list[str] | None = None,
        models: dict[str, str] | None = None,
        on_progress: Callable[[str, str, int], None] | None = None,
    ) -> BenchmarkRun:
        """Run a benchmark suite.

        Args:
            suite: The benchmark suite to run.
            providers: List of provider names to test. None = all available.
            models: Map of provider to model. None = use provider default.
            on_progress: Optional callback for progress updates.

        Returns:
            BenchmarkRun with all results.
        """
        from mrbench.adapters.base import RunOptions

        # Create run in storage
        run = self._storage.create_run(suite_path=suite.name)
        benchmark_run = BenchmarkRun(run_id=run.id, suite_name=suite.name)

        # Get adapters
        adapters: list[Adapter]
        if providers:
            adapters = []
            for provider_name in providers:
                adapter = self._registry.get(provider_name)
                if adapter is not None and adapter.is_available():
                    adapters.append(adapter)
        else:
            adapters = self._registry.get_available()

        models = models or {}

        # Run each prompt against each provider
        for prompt in suite.prompts:
            for adapter in adapters:
                # Get model
                model = models.get(adapter.name)
                if not model:
                    adapter_models = adapter.list_models()
                    model = adapter_models[0] if adapter_models else "default"

                # Create job
                from mrbench.core.storage import hash_prompt

                job = self._storage.create_job(
                    run_id=run.id,
                    provider=adapter.name,
                    model=model,
                    prompt_hash=hash_prompt(prompt.text),
                    prompt_preview=prompt.text[:100] if prompt.text else None,
                )
                self._storage.start_job(job.id)

                # Run prompt
                options = RunOptions(model=model)

                try:
                    result = adapter.run(prompt.text, options)

                    self._storage.complete_job(
                        job.id,
                        exit_code=result.exit_code,
                        error_message=result.error,
                    )

                    # Add metrics
                    self._storage.add_metric(job.id, "wall_time_ms", result.wall_time_ms, "ms")
                    if result.ttft_ms:
                        self._storage.add_metric(job.id, "ttft_ms", result.ttft_ms, "ms")
                    if result.token_count_output:
                        self._storage.add_metric(
                            job.id,
                            "output_tokens",
                            result.token_count_output,
                            "tokens",
                            is_estimated=result.tokens_estimated,
                        )

                    benchmark_run.results.append(
                        BenchmarkResult(
                            prompt_id=prompt.id,
                            provider=adapter.name,
                            model=model,
                            success=result.exit_code == 0,
                            wall_time_ms=result.wall_time_ms,
                            ttft_ms=result.ttft_ms,
                            output=result.output,
                            error=result.error,
                            token_count_input=result.token_count_input,
                            token_count_output=result.token_count_output,
                        )
                    )

                except Exception as e:
                    self._storage.complete_job(job.id, exit_code=1, error_message=str(e))
                    benchmark_run.results.append(
                        BenchmarkResult(
                            prompt_id=prompt.id,
                            provider=adapter.name,
                            model=model,
                            success=False,
                            wall_time_ms=0,
                            error=str(e),
                        )
                    )

                if on_progress:
                    on_progress(prompt.id, adapter.name, len(benchmark_run.results))

        # Complete run
        self._storage.complete_run(run.id)
        benchmark_run.completed_at = time.time()

        return benchmark_run
