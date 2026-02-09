"""Tests for llama.cpp adapter."""

from __future__ import annotations

from pathlib import Path

from mrbench.adapters import llamacpp as llamacpp_module
from mrbench.adapters.base import RunOptions
from mrbench.adapters.llamacpp import LlamaCppAdapter
from mrbench.core.executor import ExecutorResult


def test_llamacpp_adapter_identity() -> None:
    adapter = LlamaCppAdapter(binary_path="/bin/llama-cli")
    assert adapter.name == "llamacpp"
    assert adapter.display_name == "llama.cpp"


def test_get_binary_prefers_explicit_path() -> None:
    adapter = LlamaCppAdapter(binary_path="/custom/llama")
    assert adapter._get_binary() == "/custom/llama"


def test_get_binary_resolves_first_available_binary(monkeypatch) -> None:
    mapping = {
        "llama-cli": None,
        "llama-server": "/bin/llama-server",
        "main": "/bin/main",
    }
    monkeypatch.setattr(llamacpp_module.shutil, "which", lambda name: mapping.get(name))

    adapter = LlamaCppAdapter()
    assert adapter._get_binary() == "/bin/llama-server"


def test_get_binary_returns_none_when_not_found(monkeypatch) -> None:
    monkeypatch.setattr(llamacpp_module.shutil, "which", lambda _name: None)
    adapter = LlamaCppAdapter()
    assert adapter._get_binary() is None


def test_get_models_dir_uses_first_existing_candidate(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    first = home / ".cache" / "llama.cpp" / "models"
    second = home / ".local" / "share" / "llama.cpp" / "models"

    monkeypatch.setattr(llamacpp_module.Path, "home", lambda: home)

    adapter = LlamaCppAdapter()

    second.mkdir(parents=True)
    assert adapter._get_models_dir() == second

    first.mkdir(parents=True)
    assert adapter._get_models_dir() == first


def test_detect_returns_not_detected_without_binary(monkeypatch) -> None:
    adapter = LlamaCppAdapter()
    monkeypatch.setattr(adapter, "_get_binary", lambda: None)

    result = adapter.detect()

    assert result.detected is False
    assert result.error == "llama.cpp binary not found"


def test_detect_reads_version_on_success(monkeypatch) -> None:
    adapter = LlamaCppAdapter(binary_path="/bin/llama-cli")
    monkeypatch.setattr(adapter, "_get_binary", lambda: "/bin/llama-cli")
    monkeypatch.setattr(
        adapter._executor,
        "run",
        lambda _args: ExecutorResult(
            stdout="llama.cpp build 123\n",
            stderr="",
            exit_code=0,
            wall_time_ms=1.0,
        ),
    )

    result = adapter.detect()

    assert result.detected is True
    assert result.binary_path == "/bin/llama-cli"
    assert result.version == "llama.cpp build 123"
    assert result.auth_status == "authenticated"


def test_detect_sets_version_none_on_executor_failure(monkeypatch) -> None:
    adapter = LlamaCppAdapter(binary_path="/bin/llama-cli")
    monkeypatch.setattr(adapter, "_get_binary", lambda: "/bin/llama-cli")
    monkeypatch.setattr(
        adapter._executor,
        "run",
        lambda _args: ExecutorResult(
            stdout="",
            stderr="failed",
            exit_code=1,
            wall_time_ms=1.0,
        ),
    )

    result = adapter.detect()

    assert result.detected is True
    assert result.version is None


def test_list_models_returns_gguf_stems(monkeypatch, tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    (models_dir / "nested").mkdir(parents=True)
    (models_dir / "alpha.gguf").write_text("a")
    (models_dir / "nested" / "beta.gguf").write_text("b")
    (models_dir / "ignore.txt").write_text("x")

    adapter = LlamaCppAdapter()
    monkeypatch.setattr(adapter, "_get_models_dir", lambda: models_dir)

    models = adapter.list_models()
    assert set(models) == {"alpha", "beta"}


def test_list_models_returns_empty_when_models_dir_missing(monkeypatch) -> None:
    adapter = LlamaCppAdapter()
    monkeypatch.setattr(adapter, "_get_models_dir", lambda: None)
    assert adapter.list_models() == []


def test_run_returns_127_when_binary_missing(monkeypatch) -> None:
    adapter = LlamaCppAdapter()
    monkeypatch.setattr(adapter, "_get_binary", lambda: None)

    result = adapter.run("hello", RunOptions(model="m"))
    assert result.exit_code == 127
    assert result.error == "llama.cpp not found"


def test_run_returns_error_when_model_missing(monkeypatch) -> None:
    adapter = LlamaCppAdapter(binary_path="/bin/llama-cli")
    monkeypatch.setattr(adapter, "_get_binary", lambda: "/bin/llama-cli")
    monkeypatch.setattr(adapter, "_find_model", lambda _model_name: None)

    result = adapter.run("hello", RunOptions(model="missing-model"))
    assert result.exit_code == 1
    assert result.error == "Model not found: missing-model"


def test_find_model_exact_glob_and_missing(monkeypatch, tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    (models_dir / "sub").mkdir(parents=True)
    exact = models_dir / "exact.gguf"
    glob_match = models_dir / "sub" / "prefix-target-suffix.gguf"
    exact.write_text("x")
    glob_match.write_text("y")

    adapter = LlamaCppAdapter()
    monkeypatch.setattr(adapter, "_get_models_dir", lambda: models_dir)

    assert adapter._find_model("exact") == exact
    assert adapter._find_model("target") == glob_match
    assert adapter._find_model("missing") is None


def test_find_model_returns_none_without_models_dir(monkeypatch) -> None:
    adapter = LlamaCppAdapter()
    monkeypatch.setattr(adapter, "_get_models_dir", lambda: None)
    assert adapter._find_model("anything") is None


def test_llamacpp_capabilities() -> None:
    caps = LlamaCppAdapter().get_capabilities()
    assert caps.name == "llamacpp"
    assert caps.streaming is True
    assert caps.tool_calling is False
    assert caps.offline is True
