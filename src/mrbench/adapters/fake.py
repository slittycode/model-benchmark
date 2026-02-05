"""Fake adapter for testing mrbench.

Provides a mock implementation that doesn't require any external dependencies,
useful for contract testing and development.
"""

from __future__ import annotations

import time

from mrbench.adapters.base import (
    Adapter,
    AdapterCapabilities,
    DetectionResult,
    RunOptions,
    RunResult,
)


class FakeAdapter(Adapter):
    """Fake adapter for testing purposes.

    Supports multiple "models" with different behaviors:
    - fake-fast: Returns immediately
    - fake-slow: Adds artificial delay
    - fake-error: Always returns an error
    - fake-stream: Simulates streaming output
    """

    @property
    def name(self) -> str:
        return "fake"

    @property
    def display_name(self) -> str:
        return "Fake (Testing)"

    def detect(self) -> DetectionResult:
        """Fake adapter is always detected."""
        return DetectionResult(
            detected=True,
            binary_path="fake",
            version="1.0.0",
            auth_status="authenticated",
            trusted=True,
        )

    def list_models(self) -> list[str]:
        """Return list of fake models."""
        return ["fake-fast", "fake-slow", "fake-error", "fake-stream"]

    def run(self, prompt: str, options: RunOptions) -> RunResult:
        """Run a fake prompt execution."""
        model = options.model
        start_time = time.perf_counter()

        # Determine behavior based on model name
        if model == "fake-error":
            wall_time = (time.perf_counter() - start_time) * 1000
            return RunResult(
                output="",
                exit_code=1,
                wall_time_ms=wall_time,
                error="Simulated error from fake-error model",
            )

        if model == "fake-slow":
            time.sleep(0.15)  # 150ms delay

        # Generate response
        output = f"Fake response to: {prompt[:50]}{'...' if len(prompt) > 50 else ''}"

        # Simulate streaming if requested
        chunks: list[str] = []
        ttft_ms: float | None = None

        if options.stream and options.stream_callback:
            words = output.split()
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "\n")
                chunks.append(chunk)
                options.stream_callback(chunk)

                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - start_time) * 1000

                time.sleep(0.01)  # 10ms between chunks

        wall_time = (time.perf_counter() - start_time) * 1000

        # Estimate token counts (rough approximation)
        input_tokens = len(prompt.split())
        output_tokens = len(output.split())

        return RunResult(
            output=output,
            exit_code=0,
            wall_time_ms=wall_time,
            ttft_ms=ttft_ms,
            token_count_input=input_tokens,
            token_count_output=output_tokens,
            tokens_estimated=True,
            chunks=chunks,
        )

    def get_capabilities(self) -> AdapterCapabilities:
        """Return fake adapter capabilities."""
        return AdapterCapabilities(
            name=self.name,
            streaming=True,
            tool_calling=False,
            max_tokens=4096,
            max_context=8192,
            supports_system_prompt=True,
            offline=True,
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        )
