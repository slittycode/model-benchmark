"""llama.cpp adapter for mrbench.

Wraps the llama.cpp CLI (llama-cli or main binary).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from mrbench.adapters.base import (
    Adapter,
    AdapterCapabilities,
    DetectionResult,
    RunOptions,
    RunResult,
)
from mrbench.core.executor import SubprocessExecutor


class LlamaCppAdapter(Adapter):
    """Adapter for llama.cpp CLI."""

    def __init__(self, binary_path: str | None = None, timeout: float = 300.0) -> None:
        self._binary_path = binary_path
        self._timeout = timeout
        self._executor = SubprocessExecutor(timeout=timeout)

    @property
    def name(self) -> str:
        return "llamacpp"

    @property
    def display_name(self) -> str:
        return "llama.cpp"

    def _get_binary(self) -> str | None:
        if self._binary_path:
            return self._binary_path
        # Try multiple binary names
        for name in ["llama-cli", "llama-server", "main"]:
            binary = shutil.which(name)
            if binary:
                return binary
        return None

    def _get_models_dir(self) -> Path | None:
        """Get the models directory."""
        # Common locations
        candidates = [
            Path.home() / ".cache" / "llama.cpp" / "models",
            Path.home() / ".local" / "share" / "llama.cpp" / "models",
            Path.home() / "models",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    def detect(self) -> DetectionResult:
        binary = self._get_binary()
        if not binary:
            return DetectionResult(detected=False, error="llama.cpp binary not found")

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
        """List available .gguf model files."""
        models_dir = self._get_models_dir()
        if not models_dir:
            return []

        models = []
        for f in models_dir.glob("**/*.gguf"):
            models.append(f.stem)
        return models

    def run(self, prompt: str, options: RunOptions) -> RunResult:
        binary = self._get_binary()
        if not binary:
            return RunResult(output="", exit_code=127, wall_time_ms=0, error="llama.cpp not found")

        # Find model file
        model_path = self._find_model(options.model)
        if not model_path:
            return RunResult(
                output="",
                exit_code=1,
                wall_time_ms=0,
                error=f"Model not found: {options.model}",
            )

        # Keep prompt out of argv to avoid process-list exposure.
        args = [
            binary,
            "-m",
            str(model_path),
            "-p",
            "-",
            "--no-display-prompt",  # Don't echo the prompt
            "-n",
            "512",  # Max tokens
        ]

        result = self._executor.run_with_stdin_prompt(args, prompt)

        return RunResult(
            output=result.stdout,
            exit_code=result.exit_code,
            wall_time_ms=result.wall_time_ms,
            ttft_ms=result.ttft_ms,
            error=result.stderr if result.exit_code != 0 else None,
        )

    def _find_model(self, model_name: str) -> Path | None:
        """Find model file by name."""
        models_dir = self._get_models_dir()
        if not models_dir:
            return None

        # Try exact match first
        exact = models_dir / f"{model_name}.gguf"
        if exact.exists():
            return exact

        # Try glob match
        matches = list(models_dir.glob(f"**/*{model_name}*.gguf"))
        if matches:
            return matches[0]

        return None

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name=self.name,
            streaming=True,
            tool_calling=False,
            supports_system_prompt=True,
            offline=True,
        )
