"""Tests for subprocess executor behavior."""

from __future__ import annotations

import os
import sys

from mrbench.core import executor as executor_module
from mrbench.core.executor import SubprocessExecutor


def _python_cmd(code: str) -> list[str]:
    """Build a portable Python command for subprocess tests."""
    return [sys.executable, "-u", "-c", code]


def test_run_non_stream_uses_env_cwd_and_stdin(tmp_path):
    code = (
        "import os,sys; "
        "print(os.getenv('MRBENCH_TEST_ENV', 'missing')); "
        "print(os.getcwd()); "
        "print(sys.stdin.read().strip())"
    )
    executor = SubprocessExecutor(timeout=2.0, env={"MRBENCH_TEST_ENV": "set"})

    result = executor.run(
        _python_cmd(code),
        stdin="hello prompt",
        cwd=str(tmp_path),
    )

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.ttft_ms is None
    assert lines[0] == "set"
    assert lines[1] == str(tmp_path)
    assert lines[2] == "hello prompt"


def test_run_file_not_found_returns_127():
    executor = SubprocessExecutor(timeout=1.0)
    result = executor.run(["definitely-not-a-real-binary-mrbench"])

    assert result.exit_code == 127
    assert "Command not found" in result.stderr
    assert result.timed_out is False


def test_run_handles_popen_exception(monkeypatch):
    def _raise(*args, **kwargs):
        _ = (args, kwargs)
        raise RuntimeError("popen failure")

    monkeypatch.setattr(executor_module.subprocess, "Popen", _raise)
    executor = SubprocessExecutor(timeout=1.0)
    result = executor.run(["echo", "hello"])

    assert result.exit_code == 1
    assert "Execution error: popen failure" in result.stderr


def test_run_timeout_marks_timed_out_and_falls_back_to_kill(monkeypatch):
    # Force the os.killpg path to fail so the fallback process.kill() branch is exercised.
    called = {"killpg": False}

    def _killpg(_pid: int, _sig: int) -> None:
        called["killpg"] = True
        raise PermissionError("denied")

    monkeypatch.setattr(os, "killpg", _killpg)

    executor = SubprocessExecutor(timeout=0.05)
    result = executor.run(_python_cmd("import time; time.sleep(5)"))

    assert called["killpg"] is True
    assert result.timed_out is True
    assert result.exit_code != 0


def test_run_streaming_collects_chunks_and_ttft():
    code = (
        "import sys,time; "
        "data=sys.stdin.read().strip(); "
        "print(f'first:{data}', flush=True); "
        "time.sleep(0.05); "
        "print('second', flush=True); "
        "print('errline', file=sys.stderr, flush=True)"
    )
    chunks: list[str] = []
    executor = SubprocessExecutor(timeout=2.0)

    result = executor.run(
        _python_cmd(code),
        stdin="hello",
        stream_callback=chunks.append,
    )

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.ttft_ms is not None
    assert result.ttft_ms >= 0
    assert any("first:hello" in chunk for chunk in result.chunks)
    assert any("second" in chunk for chunk in result.chunks)
    assert any("first:hello" in chunk for chunk in chunks)
    assert "errline" in result.stderr


def test_run_streaming_timeout_sets_timed_out_flag():
    executor = SubprocessExecutor(timeout=0.05)
    result = executor.run(
        _python_cmd("import time; time.sleep(5)"),
        stream_callback=lambda _chunk: None,
    )

    assert result.timed_out is True
    assert result.exit_code != 0


def test_run_with_stdin_prompt_delegates_to_run():
    executor = SubprocessExecutor(timeout=1.0)
    result = executor.run_with_stdin_prompt(
        _python_cmd("import sys; print(sys.stdin.read().strip())"),
        prompt="prompt-via-stdin",
    )

    assert result.exit_code == 0
    assert "prompt-via-stdin" in result.stdout
