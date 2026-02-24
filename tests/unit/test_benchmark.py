"""Test benchmark orchestration."""

from pathlib import Path

import yaml

from mrbench.adapters.base import (
    Adapter,
    AdapterCapabilities,
    DetectionResult,
    RunOptions,
    RunResult,
)
from mrbench.adapters.registry import AdapterRegistry
from mrbench.core.benchmark import BenchmarkOrchestrator, BenchmarkPrompt, BenchmarkSuite
from mrbench.core.storage import Storage


def test_benchmark_prompt_creation():
    prompt = BenchmarkPrompt(
        id="test",
        text="Hello world",
        tags=["test"],
    )
    assert prompt.id == "test"
    assert prompt.text == "Hello world"


def test_benchmark_suite_from_yaml(tmp_path: Path):
    suite_file = tmp_path / "test.yaml"
    suite_file.write_text("""
name: Test Suite
description: A test suite

prompts:
  - id: prompt1
    text: "What is 2+2?"
    tags: [math]
  - id: prompt2
    text: "Say hello"
""")
    suite = BenchmarkSuite.from_yaml(suite_file)

    assert suite.name == "Test Suite"
    assert len(suite.prompts) == 2
    assert suite.prompts[0].id == "prompt1"
    assert suite.prompts[1].id == "prompt2"


def test_benchmark_suite_default_name(tmp_path: Path):
    suite_file = tmp_path / "mysuite.yaml"
    suite_file.write_text("""
prompts:
  - id: p1
    text: "Test"
""")
    suite = BenchmarkSuite.from_yaml(suite_file)

    assert suite.name == "mysuite"  # Uses filename


def test_hobbyist_anthropic_baseline_profile():
    suite_file = Path(__file__).resolve().parents[2] / "suites" / "hobbyist_anthropic_baseline.yaml"
    suite_data = yaml.safe_load(suite_file.read_text())

    assert suite_data["name"] == "hobbyist_anthropic_baseline"
    assert len(suite_data["prompts"]) >= 6

    anthropic_models = {
        prompt["model_overrides"]["anthropic"] for prompt in suite_data["prompts"]
    }
    assert "claude-3-haiku-20240307" in anthropic_models
    assert "claude-3-sonnet-20240229" in anthropic_models
    assert "claude-3-opus-20240229" in anthropic_models


class _ZeroMetricAdapter(Adapter):
    @property
    def name(self) -> str:
        return "zero-metric"

    def detect(self) -> DetectionResult:
        return DetectionResult(detected=True)

    def list_models(self) -> list[str]:
        return ["zero-model"]

    def run(self, prompt: str, options: RunOptions) -> RunResult:
        return RunResult(
            output="ok",
            exit_code=0,
            wall_time_ms=1.0,
            ttft_ms=0.0,
            token_count_input=0,
            token_count_output=0,
            tokens_estimated=True,
        )

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(name=self.name, offline=True)


def test_orchestrator_persists_zero_value_metrics(tmp_path: Path):
    registry = AdapterRegistry()
    registry.register(_ZeroMetricAdapter())
    with Storage(tmp_path / "metrics.db") as storage:
        orchestrator = BenchmarkOrchestrator(registry=registry, storage=storage)

        suite = BenchmarkSuite(
            name="zero-metric-suite",
            description="",
            prompts=[BenchmarkPrompt(id="p1", text="hello")],
        )
        run = orchestrator.run_suite(suite)

        jobs = storage.get_jobs_for_run(run.run_id)
        assert len(jobs) == 1
        metrics = {m.metric_name: m.metric_value for m in storage.get_job_metrics(jobs[0].id)}

        assert metrics["wall_time_ms"] == 1.0
        assert metrics["ttft_ms"] == 0.0
        assert metrics["output_tokens"] == 0.0
