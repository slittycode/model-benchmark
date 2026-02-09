"""Ollama adapter for mrbench.

Wraps the Ollama CLI for local model inference.
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


class OllamaAdapter(Adapter):
    """Adapter for Ollama local model runner."""

    def __init__(self, binary_path: str | None = None, timeout: float = 300.0) -> None:
        """Initialize Ollama adapter.

        Args:
            binary_path: Override path to ollama binary.
            timeout: Default timeout for commands.
        """
        self._binary_path = binary_path
        self._timeout = timeout
        self._executor = SubprocessExecutor(timeout=timeout)
        self._cached_binary: str | None = None

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama"

    def _get_binary(self) -> str | None:
        """Find the ollama binary."""
        if self._binary_path:
            return self._binary_path
        if self._cached_binary:
            return self._cached_binary
        self._cached_binary = shutil.which("ollama")
        return self._cached_binary

    def _run_command(self, args: list[str], stdin: str | None = None) -> ExecutorResult:
        """Run an ollama command."""
        from mrbench.core.executor import ExecutorResult

        binary = self._get_binary()
        if not binary:
            return ExecutorResult(
                stdout="",
                stderr="ollama binary not found",
                exit_code=127,
                wall_time_ms=0,
            )
        return self._executor.run([binary, *args], stdin=stdin)

    def _run_version_check(self) -> str | None:
        """Get ollama version."""
        result = self._run_command(["--version"])
        if result.exit_code == 0:
            # Parse version from output like "ollama version 0.1.0"
            output = result.stdout.strip()
            if "version" in output.lower():
                parts = output.split()
                if len(parts) >= 3:
                    return parts[-1]
            return output
        return None

    def detect(self) -> DetectionResult:
        """Detect if Ollama is installed."""
        binary = self._get_binary()

        if not binary:
            return DetectionResult(
                detected=False,
                error="ollama binary not found in PATH",
            )

        # Check if binary is in a trusted location
        trusted_paths = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]
        trusted = any(binary.startswith(p) for p in trusted_paths)

        # Get version
        version = self._run_version_check()

        # Check auth status by listing models
        # If we can list models, we're "authenticated" (Ollama doesn't require auth)
        list_result = self._run_command(["list"])
        auth_status = "authenticated" if list_result.exit_code == 0 else "unknown"

        return DetectionResult(
            detected=True,
            binary_path=binary,
            version=version,
            auth_status=auth_status,
            trusted=trusted,
        )

    def list_models(self) -> list[str]:
        """List available Ollama models."""
        result = self._run_command(["list"])

        if result.exit_code != 0:
            return []

        models: list[str] = []
        lines = result.stdout.strip().split("\n")

        # Skip header line
        for line in lines[1:]:
            if line.strip():
                # First column is the model name
                parts = line.split()
                if parts:
                    models.append(parts[0])

        return models

    def run(self, prompt: str, options: RunOptions) -> RunResult:
        """Run a prompt through Ollama."""
        binary = self._get_binary()
        if not binary:
            return RunResult(output="", exit_code=127, wall_time_ms=0, error="ollama not found")

        # Keep prompt out of argv to avoid process-list exposure.
        args = [binary, "run", options.model]

        # Execute
        if options.stream and options.stream_callback:
            result = self._executor.run(
                args,
                stdin=prompt,
                stream_callback=options.stream_callback,
            )
        else:
            result = self._executor.run_with_stdin_prompt(args, prompt)

        # Build result
        return RunResult(
            output=result.stdout,
            exit_code=result.exit_code,
            wall_time_ms=result.wall_time_ms,
            ttft_ms=result.ttft_ms,
            error=result.stderr if result.exit_code != 0 else None,
            chunks=result.chunks,
        )

    def get_capabilities(self) -> AdapterCapabilities:
        """Return Ollama capabilities."""
        return AdapterCapabilities(
            name=self.name,
            streaming=True,
            tool_calling=False,  # Ollama supports it but not via CLI easily
            max_tokens=None,  # Model-dependent
            max_context=None,  # Model-dependent
            supports_system_prompt=True,
            offline=True,  # Local inference
            cost_per_1k_input=0.0,
            cost_per_1k_output=0.0,
        )


# For type hints
from mrbench.core.executor import ExecutorResult  # noqa: E402
