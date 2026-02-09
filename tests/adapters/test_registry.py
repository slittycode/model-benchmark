"""Tests for adapter registry."""

from __future__ import annotations

from dataclasses import dataclass

from mrbench.adapters.base import AdapterCapabilities, DetectionResult, RunOptions, RunResult
from mrbench.adapters.registry import AdapterRegistry, get_default_registry, reset_default_registry


@dataclass
class _StubAdapter:
    name: str
    detected: bool = True
    available: bool = True

    @property
    def display_name(self) -> str:
        return self.name.upper()

    def detect(self) -> DetectionResult:
        return DetectionResult(detected=self.detected, binary_path=f"/bin/{self.name}")

    def list_models(self) -> list[str]:
        return [f"{self.name}-model"]

    def run(self, prompt: str, options: RunOptions) -> RunResult:
        _ = (prompt, options)
        return RunResult(output="ok", exit_code=0, wall_time_ms=1.0)

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(name=self.name, offline=True)

    def is_available(self) -> bool:
        return self.available


def test_registry_register_get_and_list() -> None:
    registry = AdapterRegistry()
    alpha = _StubAdapter("alpha")
    beta = _StubAdapter("beta")

    registry.register(alpha)
    registry.register(beta)

    assert registry.get("alpha") is alpha
    assert registry.get("missing") is None
    assert [adapter.name for adapter in registry.list_all()] == ["alpha", "beta"]
    assert registry.list_names() == ["alpha", "beta"]


def test_registry_detect_all_filters_detected_only() -> None:
    registry = AdapterRegistry()
    registry.register(_StubAdapter("detected", detected=True))
    registry.register(_StubAdapter("hidden", detected=False))

    results = registry.detect_all()
    assert len(results) == 1
    assert results[0].binary_path == "/bin/detected"


def test_registry_get_available_filters_by_adapter_availability() -> None:
    registry = AdapterRegistry()
    available = _StubAdapter("available", available=True)
    unavailable = _StubAdapter("unavailable", available=False)
    registry.register(available)
    registry.register(unavailable)

    adapters = registry.get_available()
    assert adapters == [available]


def test_default_registry_singleton_and_reset() -> None:
    reset_default_registry()
    first = get_default_registry()
    second = get_default_registry()

    assert first is second
    names = first.list_names()
    # Core built-ins are always present.
    assert "fake" in names
    assert "ollama" in names
    assert "claude" in names
    assert "codex" in names
    assert "gemini" in names
    assert "goose" in names
    assert "opencode" in names
    assert "llamacpp" in names
    assert "vllm" in names

    reset_default_registry()
    third = get_default_registry()
    assert third is not first
