"""Claude Code adapter for mrbench.

Wraps the Claude Code CLI (claude command).
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


class ClaudeAdapter(Adapter):
    """Adapter for Claude Code CLI."""

    def __init__(self, binary_path: str | None = None, timeout: float = 300.0) -> None:
        self._binary_path = binary_path
        self._timeout = timeout
        self._executor = SubprocessExecutor(timeout=timeout)

    @property
    def name(self) -> str:
        return "claude"

    @property
    def display_name(self) -> str:
        return "Claude Code"

    def _get_binary(self) -> str | None:
        if self._binary_path:
            return self._binary_path
        return shutil.which("claude")

    def detect(self) -> DetectionResult:
        binary = self._get_binary()
        if not binary:
            return DetectionResult(detected=False, error="claude binary not found")

        # Get version
        result = self._executor.run([binary, "--version"])
        version = result.stdout.strip() if result.exit_code == 0 else None

        return DetectionResult(
            detected=True,
            binary_path=binary,
            version=version,
            auth_status="unknown",  # Would need to try a command to check
            trusted=True,
        )

    def list_models(self) -> list[str]:
        # Claude Code doesn't have a list models command
        # Return common model names
        return ["claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku"]

    def run(self, prompt: str, options: RunOptions) -> RunResult:
        binary = self._get_binary()
        if not binary:
            return RunResult(output="", exit_code=127, wall_time_ms=0, error="claude not found")

        # Keep prompt out of argv to avoid process-list exposure.
        args = [binary, "-p", "-", "--output-format", "text"]

        result = self._executor.run_with_stdin_prompt(args, prompt)

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
            max_tokens=8192,
            max_context=200000,
            supports_system_prompt=True,
            offline=False,
        )
