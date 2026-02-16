"""Tests for vLLM adapter."""

from __future__ import annotations

from mrbench.adapters.base import RunOptions
from mrbench.adapters.vllm import VllmAdapter
from mrbench.core.executor import ExecutorResult


def test_vllm_adapter_identity() -> None:
    adapter = VllmAdapter(binary_path="/bin/vllm")
    assert adapter.name == "vllm"
    assert adapter.display_name == "vLLM"


def test_vllm_detect_without_binary(monkeypatch) -> None:
    adapter = VllmAdapter()
    monkeypatch.setattr(adapter, "_get_binary", lambda: None)

    result = adapter.detect()
    assert result.detected is False
    assert result.error == "vllm binary not found"


def test_vllm_detect_with_binary_and_version(monkeypatch) -> None:
    adapter = VllmAdapter(binary_path="/bin/vllm")
    monkeypatch.setattr(adapter, "_get_binary", lambda: "/bin/vllm")
    monkeypatch.setattr(
        adapter._executor,
        "run",
        lambda _args: ExecutorResult(
            stdout="vllm 0.5.0\n",
            stderr="",
            exit_code=0,
            wall_time_ms=1.0,
        ),
    )

    result = adapter.detect()
    assert result.detected is True
    assert result.binary_path == "/bin/vllm"
    assert result.version == "vllm 0.5.0"
    assert result.auth_status == "authenticated"


def test_vllm_list_models_contains_expected_defaults() -> None:
    models = VllmAdapter().list_models()
    assert "meta-llama/Llama-2-7b-chat-hf" in models
    assert "mistralai/Mistral-7B-v0.1" in models


def test_vllm_run_without_binary(monkeypatch) -> None:
    adapter = VllmAdapter()
    monkeypatch.setattr(adapter, "_get_binary", lambda: None)

    result = adapter.run("hello", RunOptions(model="m"))
    assert result.exit_code == 127
    assert result.error == "vllm not found"


def test_vllm_run_builds_args_with_model_and_propagates_result(monkeypatch) -> None:
    adapter = VllmAdapter(binary_path="/bin/vllm")
    monkeypatch.setattr(adapter, "_get_binary", lambda: "/bin/vllm")

    calls: list[tuple[list[str], str]] = []

    def _run(
        args: list[str],
        prompt: str,
        cwd: str | None = None,
        stream_callback: object | None = None,
        timeout: float | None = None,
    ) -> ExecutorResult:
        _ = (cwd, stream_callback, timeout)
        calls.append((args, prompt))
        return ExecutorResult(
            stdout="ok",
            stderr="",
            exit_code=0,
            wall_time_ms=8.0,
            ttft_ms=2.0,
        )

    monkeypatch.setattr(adapter._executor, "run_with_stdin_prompt", _run)
    success = adapter.run("prompt text", RunOptions(model="my-model"))

    assert success.exit_code == 0
    assert success.output == "ok"
    assert success.ttft_ms == 2.0
    assert success.error is None
    assert calls == [
        (
            ["/bin/vllm", "complete", "--quick", "-", "--model", "my-model"],
            "prompt text",
        )
    ]

    monkeypatch.setattr(
        adapter._executor,
        "run_with_stdin_prompt",
        lambda _args, _prompt, **_kwargs: ExecutorResult(
            stdout="",
            stderr="failed",
            exit_code=3,
            wall_time_ms=4.0,
        ),
    )
    failure = adapter.run("prompt text", RunOptions(model="my-model"))
    assert failure.exit_code == 3
    assert failure.error == "failed"


def test_vllm_capabilities() -> None:
    caps = VllmAdapter().get_capabilities()
    assert caps.name == "vllm"
    assert caps.streaming is True
    assert caps.tool_calling is False
    assert caps.offline is True
