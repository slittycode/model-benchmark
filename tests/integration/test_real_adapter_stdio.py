"""Opt-in integration tests for real subprocess adapter invocation contracts."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from pathlib import Path

import pytest

from mrbench.adapters.base import Adapter, RunOptions
from mrbench.adapters.claude import ClaudeAdapter
from mrbench.adapters.codex import CodexAdapter
from mrbench.adapters.gemini import GeminiAdapter
from mrbench.adapters.goose import GooseAdapter
from mrbench.adapters.llamacpp import LlamaCppAdapter
from mrbench.adapters.ollama import OllamaAdapter
from mrbench.adapters.opencode import OpenCodeAdapter
from mrbench.adapters.vllm import VllmAdapter

pytestmark = [pytest.mark.real_adapters]

if os.getenv("MRBENCH_RUN_REAL_ADAPTER_TESTS") != "1":
    pytest.skip(
        "Set MRBENCH_RUN_REAL_ADAPTER_TESTS=1 to enable real adapter subprocess contract tests",
        allow_module_level=True,
    )


def _make_echo_binary(tmp_path: Path) -> str:
    script = tmp_path / "echo_cli.py"
    script.write_text(
        """#!/usr/bin/env python3
import json
import sys

payload = {"argv": sys.argv[1:], "stdin": sys.stdin.read()}
print(json.dumps(payload))
""",
    )
    mode = script.stat().st_mode
    script.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(script)


@pytest.mark.parametrize(
    ("factory", "model"),
    [
        (lambda binary: ClaudeAdapter(binary_path=binary), "claude-3-5-sonnet"),
        (lambda binary: CodexAdapter(binary_path=binary), "o4-mini"),
        (lambda binary: GeminiAdapter(binary_path=binary), "gemini-2.5-pro"),
        (lambda binary: GooseAdapter(binary_path=binary), "default"),
        (lambda binary: OllamaAdapter(binary_path=binary), "llama3.2"),
        (lambda binary: OpenCodeAdapter(binary_path=binary), "default"),
        (lambda binary: VllmAdapter(binary_path=binary), "meta-llama/Llama-2-7b-chat-hf"),
        (lambda binary: LlamaCppAdapter(binary_path=binary), "llama-3"),
    ],
)
def test_adapters_send_prompt_via_stdin(
    tmp_path: Path,
    factory: Callable[[str], Adapter],
    model: str,
) -> None:
    binary = _make_echo_binary(tmp_path)
    adapter = factory(binary)
    prompt = "secret prompt text should not be in argv"

    if isinstance(adapter, LlamaCppAdapter):
        adapter._find_model = lambda _: tmp_path / "fake.gguf"  # type: ignore[method-assign]

    result = adapter.run(prompt, RunOptions(model=model))

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["stdin"] == prompt
    assert all(prompt not in arg for arg in payload["argv"])
