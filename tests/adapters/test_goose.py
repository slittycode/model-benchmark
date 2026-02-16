"""Tests for Goose adapter."""

from __future__ import annotations

from mrbench.adapters.base import RunOptions
from mrbench.adapters.goose import GooseAdapter
from mrbench.core.executor import ExecutorResult


def test_goose_adapter_identity() -> None:
    adapter = GooseAdapter(binary_path="/bin/goose")
    assert adapter.name == "goose"
    assert adapter.display_name == "Goose"


def test_goose_detect_without_binary(monkeypatch) -> None:
    adapter = GooseAdapter()
    monkeypatch.setattr(adapter, "_get_binary", lambda: None)

    result = adapter.detect()
    assert result.detected is False
    assert result.error == "goose binary not found"


def test_goose_detect_with_binary_and_version(monkeypatch) -> None:
    adapter = GooseAdapter(binary_path="/bin/goose")
    monkeypatch.setattr(adapter, "_get_binary", lambda: "/bin/goose")
    monkeypatch.setattr(
        adapter._executor,
        "run",
        lambda _args: ExecutorResult(
            stdout="goose 1.2.3\n",
            stderr="",
            exit_code=0,
            wall_time_ms=1.0,
        ),
    )

    result = adapter.detect()
    assert result.detected is True
    assert result.binary_path == "/bin/goose"
    assert result.version == "goose 1.2.3"
    assert result.auth_status == "unknown"


def test_goose_list_models_is_empty() -> None:
    assert GooseAdapter().list_models() == []


def test_goose_run_without_binary(monkeypatch) -> None:
    adapter = GooseAdapter()
    monkeypatch.setattr(adapter, "_get_binary", lambda: None)

    result = adapter.run("hello", RunOptions(model="ignored"))
    assert result.exit_code == 127
    assert result.error == "goose not found"


def test_goose_run_success_and_error_propagation(monkeypatch) -> None:
    adapter = GooseAdapter(binary_path="/bin/goose")
    monkeypatch.setattr(adapter, "_get_binary", lambda: "/bin/goose")

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
            stdout="ok output",
            stderr="",
            exit_code=0,
            wall_time_ms=5.0,
        )

    monkeypatch.setattr(adapter._executor, "run_with_stdin_prompt", _run)
    success = adapter.run("prompt text", RunOptions(model="ignored"))

    assert success.exit_code == 0
    assert success.output == "ok output"
    assert success.error is None
    assert calls == [(["/bin/goose", "run", "-"], "prompt text")]

    monkeypatch.setattr(
        adapter._executor,
        "run_with_stdin_prompt",
        lambda _args, _prompt, **_kwargs: ExecutorResult(
            stdout="",
            stderr="boom",
            exit_code=1,
            wall_time_ms=3.0,
        ),
    )
    failure = adapter.run("prompt text", RunOptions(model="ignored"))
    assert failure.exit_code == 1
    assert failure.error == "boom"


def test_goose_capabilities() -> None:
    caps = GooseAdapter().get_capabilities()
    assert caps.name == "goose"
    assert caps.streaming is True
    assert caps.tool_calling is True
    assert caps.offline is False
