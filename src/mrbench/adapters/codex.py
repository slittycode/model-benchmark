"""Codex CLI adapter for mrbench.

Wraps the OpenAI Codex CLI.
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


class CodexAdapter(Adapter):
    """Adapter for OpenAI Codex CLI."""

    def __init__(self, binary_path: str | None = None, timeout: float = 300.0) -> None:
        self._binary_path = binary_path
        self._timeout = timeout
        self._executor = SubprocessExecutor(timeout=timeout)

    @property
    def name(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "Codex CLI"

    def _get_binary(self) -> str | None:
        if self._binary_path:
            return self._binary_path
        return shutil.which("codex")

    def detect(self) -> DetectionResult:
        binary = self._get_binary()
        if not binary:
            return DetectionResult(detected=False, error="codex binary not found")

        result = self._executor.run([binary, "--version"])
        version = result.stdout.strip() if result.exit_code == 0 else None

        return DetectionResult(
            detected=True,
            binary_path=binary,
            version=version,
            auth_status="unknown",
            trusted=True,
        )

    def list_models(self) -> list[str]:
        return ["o4-mini", "o3", "gpt-4.1"]

    def run(self, prompt: str, options: RunOptions) -> RunResult:
        binary = self._get_binary()
        if not binary:
            return RunResult(output="", exit_code=127, wall_time_ms=0, error="codex not found")

        # codex exec "prompt" for non-interactive
        args = [binary, "exec", prompt]

        result = self._executor.run(args)

        return RunResult(
            output=result.stdout,
            exit_code=result.exit_code,
            wall_time_ms=result.wall_time_ms,
            error=result.stderr if result.exit_code != 0 else None,
        )

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name=self.name,
            streaming=True,
            tool_calling=True,
            max_tokens=16384,
            max_context=128000,
            supports_system_prompt=True,
            offline=False,
        )
