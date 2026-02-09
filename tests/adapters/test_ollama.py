"""Tests for Ollama adapter."""

from __future__ import annotations

from mrbench.adapters.base import RunOptions
from mrbench.adapters.ollama import OllamaAdapter
from mrbench.core.executor import ExecutorResult


def test_ollama_adapter_identity() -> None:
    adapter = OllamaAdapter(binary_path="/bin/ollama")
    assert adapter.name == "ollama"
    assert adapter.display_name == "Ollama"


def test_get_binary_uses_cache(monkeypatch) -> None:
    calls = {"count": 0}

    def _which(name: str) -> str | None:
        calls["count"] += 1
        return "/bin/ollama" if name == "ollama" else None

    from mrbench.adapters import ollama as ollama_module

    monkeypatch.setattr(ollama_module.shutil, "which", _which)
    adapter = OllamaAdapter()

    assert adapter._get_binary() == "/bin/ollama"
    assert adapter._get_binary() == "/bin/ollama"
    assert calls["count"] == 1


def test_run_command_returns_127_when_binary_missing(monkeypatch) -> None:
    adapter = OllamaAdapter()
    monkeypatch.setattr(adapter, "_get_binary", lambda: None)

    result = adapter._run_command(["list"])
    assert result.exit_code == 127
    assert result.stderr == "ollama binary not found"


def test_run_version_check_parsing_variants(monkeypatch) -> None:
    adapter = OllamaAdapter(binary_path="/bin/ollama")

    # Standard "ollama version X.Y.Z" output.
    monkeypatch.setattr(
        adapter,
        "_run_command",
        lambda _args: ExecutorResult(
            stdout="ollama version 0.4.1\n",
            stderr="",
            exit_code=0,
            wall_time_ms=1.0,
        ),
    )
    assert adapter._run_version_check() == "0.4.1"

    # Non-standard output should be returned as-is.
    monkeypatch.setattr(
        adapter,
        "_run_command",
        lambda _args: ExecutorResult(
            stdout="custom-build-string\n",
            stderr="",
            exit_code=0,
            wall_time_ms=1.0,
        ),
    )
    assert adapter._run_version_check() == "custom-build-string"

    # Failure returns None.
    monkeypatch.setattr(
        adapter,
        "_run_command",
        lambda _args: ExecutorResult(
            stdout="",
            stderr="failed",
            exit_code=1,
            wall_time_ms=1.0,
        ),
    )
    assert adapter._run_version_check() is None


def test_detect_without_binary(monkeypatch) -> None:
    adapter = OllamaAdapter()
    monkeypatch.setattr(adapter, "_get_binary", lambda: None)

    result = adapter.detect()
    assert result.detected is False
    assert result.error == "ollama binary not found in PATH"


def test_detect_sets_auth_unknown_when_list_fails(monkeypatch) -> None:
    adapter = OllamaAdapter(binary_path="/tmp/ollama")
    monkeypatch.setattr(adapter, "_get_binary", lambda: "/tmp/ollama")
    monkeypatch.setattr(adapter, "_run_version_check", lambda: "0.5.0")

    def _run_command(args: list[str], stdin: str | None = None) -> ExecutorResult:
        _ = stdin
        if args == ["list"]:
            return ExecutorResult(stdout="", stderr="not running", exit_code=1, wall_time_ms=1.0)
        return ExecutorResult(stdout="", stderr="", exit_code=0, wall_time_ms=1.0)

    monkeypatch.setattr(adapter, "_run_command", _run_command)

    result = adapter.detect()
    assert result.detected is True
    assert result.binary_path == "/tmp/ollama"
    assert result.version == "0.5.0"
    assert result.auth_status == "unknown"
    assert result.trusted is False


def test_list_models_returns_empty_on_error(monkeypatch) -> None:
    adapter = OllamaAdapter()
    monkeypatch.setattr(
        adapter,
        "_run_command",
        lambda _args, stdin=None: ExecutorResult(
            stdout="",
            stderr="error",
            exit_code=1,
            wall_time_ms=1.0,
        ),
    )

    assert adapter.list_models() == []


def test_list_models_parses_model_names(monkeypatch) -> None:
    adapter = OllamaAdapter()
    output = (
        "NAME ID SIZE MODIFIED\n"
        "llama3.2 abc123 4.7 GB 2 days ago\n"
        "mistral def456 4.1 GB 1 day ago\n"
    )
    monkeypatch.setattr(
        adapter,
        "_run_command",
        lambda _args, stdin=None: ExecutorResult(
            stdout=output,
            stderr="",
            exit_code=0,
            wall_time_ms=1.0,
        ),
    )

    assert adapter.list_models() == ["llama3.2", "mistral"]


def test_run_without_binary_returns_127(monkeypatch) -> None:
    adapter = OllamaAdapter()
    monkeypatch.setattr(adapter, "_get_binary", lambda: None)

    result = adapter.run("prompt", RunOptions(model="llama3.2"))
    assert result.exit_code == 127
    assert result.error == "ollama not found"


def test_run_stream_path_uses_executor_run(monkeypatch) -> None:
    adapter = OllamaAdapter(binary_path="/bin/ollama")
    monkeypatch.setattr(adapter, "_get_binary", lambda: "/bin/ollama")

    calls: list[tuple[list[str], str]] = []

    def _run(
        args: list[str],
        stdin: str | None = None,
        cwd: str | None = None,
        stream_callback: object | None = None,
    ) -> ExecutorResult:
        _ = (cwd, stream_callback)
        calls.append((args, stdin or ""))
        return ExecutorResult(
            stdout="streamed",
            stderr="",
            exit_code=0,
            wall_time_ms=10.0,
            ttft_ms=2.5,
            chunks=["a", "b"],
        )

    monkeypatch.setattr(adapter._executor, "run", _run)

    result = adapter.run(
        "prompt text",
        RunOptions(model="llama3.2", stream=True, stream_callback=lambda _chunk: None),
    )
    assert calls == [(["/bin/ollama", "run", "llama3.2"], "prompt text")]
    assert result.output == "streamed"
    assert result.ttft_ms == 2.5
    assert result.chunks == ["a", "b"]


def test_ollama_capabilities() -> None:
    caps = OllamaAdapter().get_capabilities()
    assert caps.name == "ollama"
    assert caps.streaming is True
    assert caps.offline is True
    assert caps.cost_per_1k_input == 0.0
