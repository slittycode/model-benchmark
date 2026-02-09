"""vLLM adapter for mrbench.

Wraps the vLLM CLI for running local LLM inference.
"""

from __future__ import annotations

import shutil

from mrbench.adapters.base import (
    Adapter,
    AdapterCapabilities,
    DetectionResult,
    RunOptions,
    RunResult,
)
from mrbench.core.executor import SubprocessExecutor


class VllmAdapter(Adapter):
    """Adapter for vLLM CLI."""

    def __init__(self, binary_path: str | None = None, timeout: float = 300.0) -> None:
        self._binary_path = binary_path
        self._timeout = timeout
        self._executor = SubprocessExecutor(timeout=timeout)

    @property
    def name(self) -> str:
        return "vllm"

    @property
    def display_name(self) -> str:
        return "vLLM"

    def _get_binary(self) -> str | None:
        if self._binary_path:
            return self._binary_path
        return shutil.which("vllm")

    def detect(self) -> DetectionResult:
        binary = self._get_binary()
        if not binary:
            return DetectionResult(detected=False, error="vllm binary not found")

        result = self._executor.run([binary, "--version"])
        version = result.stdout.strip() if result.exit_code == 0 else None

        return DetectionResult(
            detected=True,
            binary_path=binary,
            version=version,
            auth_status="authenticated",  # Local, no auth needed
            trusted=True,
        )

    def list_models(self) -> list[str]:
        """List models - vLLM uses HuggingFace model IDs."""
        # vLLM typically uses HF model IDs, return common ones
        return [
            "meta-llama/Llama-2-7b-chat-hf",
            "mistralai/Mistral-7B-v0.1",
        ]

    def run(self, prompt: str, options: RunOptions) -> RunResult:
        binary = self._get_binary()
        if not binary:
            return RunResult(output="", exit_code=127, wall_time_ms=0, error="vllm not found")

        # Keep prompt out of argv to avoid process-list exposure.
        args = [
            binary,
            "complete",
            "--quick",
            "-",
        ]

        if options.model:
            args.extend(["--model", options.model])

        result = self._executor.run_with_stdin_prompt(args, prompt)

        return RunResult(
            output=result.stdout,
            exit_code=result.exit_code,
            wall_time_ms=result.wall_time_ms,
            ttft_ms=result.ttft_ms,
            error=result.stderr if result.exit_code != 0 else None,
        )

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name=self.name,
            streaming=True,
            tool_calling=False,
            supports_system_prompt=True,
            offline=True,  # Local inference
        )
