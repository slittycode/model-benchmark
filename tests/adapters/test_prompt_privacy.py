"""Prompt privacy tests for adapter command construction.

These tests ensure prompt text is never passed as a command-line argument.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mrbench.adapters.base import RunOptions
from mrbench.adapters.claude import ClaudeAdapter
from mrbench.adapters.codex import CodexAdapter
from mrbench.adapters.gemini import GeminiAdapter
from mrbench.adapters.goose import GooseAdapter
from mrbench.adapters.llamacpp import LlamaCppAdapter
from mrbench.adapters.ollama import OllamaAdapter
from mrbench.adapters.opencode import OpenCodeAdapter
from mrbench.adapters.vllm import VllmAdapter
from mrbench.core.executor import ExecutorResult


class SpyExecutor:
    """Captures executor inputs for assertion."""

    def __init__(self) -> None:
        self.last_args: list[str] = []
        self.stdin_value: str | None = None
        self.last_timeout: float | None = None

    def run(
        self,
        args: list[str],
        stdin: str | None = None,
        cwd: str | None = None,
        stream_callback: object | None = None,
        timeout: float | None = None,
    ) -> ExecutorResult:
        self.last_args = args
        self.stdin_value = stdin
        self.last_timeout = timeout
        return ExecutorResult(stdout="ok", stderr="", exit_code=0, wall_time_ms=1.0)

    def run_with_stdin_prompt(
        self,
        args: list[str],
        prompt: str,
        cwd: str | None = None,
        stream_callback: object | None = None,
        timeout: float | None = None,
    ) -> ExecutorResult:
        self.last_args = args
        self.stdin_value = prompt
        self.last_timeout = timeout
        return ExecutorResult(stdout="ok", stderr="", exit_code=0, wall_time_ms=1.0)


@pytest.mark.parametrize(
    ("adapter", "model"),
    [
        (ClaudeAdapter(binary_path="/bin/claude"), "claude-3-5-sonnet"),
        (CodexAdapter(binary_path="/bin/codex"), "o4-mini"),
        (GeminiAdapter(binary_path="/bin/gemini"), "gemini-2.5-pro"),
        (GooseAdapter(binary_path="/bin/goose"), "default"),
        (OllamaAdapter(binary_path="/bin/ollama"), "llama3.2"),
        (OpenCodeAdapter(binary_path="/bin/opencode"), "default"),
        (VllmAdapter(binary_path="/bin/vllm"), "meta-llama/Llama-2-7b-chat-hf"),
    ],
)
def test_adapter_run_keeps_prompt_out_of_argv(adapter: object, model: str) -> None:
    prompt = "TOP-SECRET: this prompt must never appear in argv"
    spy = SpyExecutor()
    adapter._executor = spy  # type: ignore[attr-defined]

    result = adapter.run(
        prompt,
        RunOptions(model=model, timeout=42.5),
    )  # type: ignore[attr-defined]

    assert result.exit_code == 0
    assert all(prompt not in arg for arg in spy.last_args)
    assert spy.stdin_value == prompt
    assert spy.last_timeout == 42.5


def test_llamacpp_run_keeps_prompt_out_of_argv() -> None:
    prompt = "TOP-SECRET: this prompt must never appear in argv"
    adapter = LlamaCppAdapter(binary_path="/bin/llama-cli")
    spy = SpyExecutor()
    adapter._executor = spy
    adapter._find_model = lambda model_name: Path("/tmp/model.gguf")  # type: ignore[method-assign]

    result = adapter.run(prompt, RunOptions(model="llama-3", timeout=17.25))

    assert result.exit_code == 0
    assert all(prompt not in arg for arg in spy.last_args)
    assert spy.stdin_value == prompt
    assert spy.last_timeout == 17.25
