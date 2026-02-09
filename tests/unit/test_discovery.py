"""Tests for discovery behavior."""

from __future__ import annotations

from pathlib import Path

from mrbench.core import discovery as discovery_module
from mrbench.core.discovery import ConfigCheckResult, ConfigDetector
from mrbench.core.executor import ExecutorResult


def test_discover_cli_tools_skips_auth_checks_by_default(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "codex-config"
    config_dir.mkdir()

    monkeypatch.setattr(discovery_module, "CONFIG_LOCATIONS", {"codex": [str(config_dir)]})
    monkeypatch.setattr(discovery_module, "AUTH_CHECK_COMMANDS", {"codex": ["codex", "--version"]})
    monkeypatch.setattr(
        discovery_module.shutil,
        "which",
        lambda tool: "/bin/codex" if tool == "codex" else None,
    )

    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> ExecutorResult:
        calls.append(args)
        return ExecutorResult(stdout="ok", stderr="", exit_code=0, wall_time_ms=1.0)

    detector = ConfigDetector()
    detector._executor.run = fake_run  # type: ignore[method-assign]

    results = detector.discover_cli_tools()

    assert not calls
    assert len(results["installed"]) == 1
    assert results["ready"] == []


def test_discover_cli_tools_runs_auth_checks_when_enabled(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "codex-config"
    config_dir.mkdir()

    monkeypatch.setattr(discovery_module, "CONFIG_LOCATIONS", {"codex": [str(config_dir)]})
    monkeypatch.setattr(discovery_module, "AUTH_CHECK_COMMANDS", {"codex": ["codex", "--version"]})
    monkeypatch.setattr(
        discovery_module.shutil,
        "which",
        lambda tool: "/bin/codex" if tool == "codex" else None,
    )

    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> ExecutorResult:
        calls.append(args)
        return ExecutorResult(stdout="ok", stderr="", exit_code=0, wall_time_ms=1.0)

    detector = ConfigDetector()
    detector._executor.run = fake_run  # type: ignore[method-assign]

    results = detector.discover_cli_tools(check_auth=True)

    assert calls == [["codex", "--version"]]
    assert len(results["ready"]) == 1
    assert results["ready"][0]["name"] == "codex"


def test_check_provider_resolves_binary_alias_for_azure(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "azure-config"
    config_dir.mkdir()

    monkeypatch.setattr(discovery_module, "CONFIG_LOCATIONS", {"azure": [str(config_dir)]})
    monkeypatch.setattr(
        discovery_module, "AUTH_CHECK_COMMANDS", {"azure": ["az", "account", "show"]}
    )
    monkeypatch.setattr(
        discovery_module.shutil,
        "which",
        lambda tool: "/bin/az" if tool == "az" else None,
    )

    detector = ConfigDetector()
    result = detector.check_provider("azure")

    assert result.has_binary is True
    assert result.has_config is True
    assert result.config_path == str(config_dir)


def test_discover_az_binary_uses_azure_config_and_auth(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "azure-config"
    config_dir.mkdir()

    monkeypatch.setattr(discovery_module, "CONFIG_LOCATIONS", {"azure": [str(config_dir)]})
    monkeypatch.setattr(
        discovery_module, "AUTH_CHECK_COMMANDS", {"azure": ["az", "account", "show"]}
    )
    monkeypatch.setattr(
        discovery_module.shutil,
        "which",
        lambda tool: "/bin/az" if tool == "az" else None,
    )

    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> ExecutorResult:
        calls.append(args)
        return ExecutorResult(stdout="ok", stderr="", exit_code=0, wall_time_ms=1.0)

    detector = ConfigDetector()
    detector._executor.run = fake_run  # type: ignore[method-assign]

    results = detector.discover_cli_tools(check_auth=True)

    assert len(results["installed"]) == 1
    assert results["installed"][0]["name"] == "az"
    assert results["installed"][0]["has_config"] is True
    assert results["installed"][0]["config_path"] == str(config_dir)
    assert calls == [["az", "account", "show"]]


def test_discover_llamacpp_alias_uses_canonical_config(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "llama-models"
    model_dir.mkdir()

    monkeypatch.setattr(discovery_module, "CONFIG_LOCATIONS", {"llamacpp": [str(model_dir)]})
    monkeypatch.setattr(discovery_module, "AUTH_CHECK_COMMANDS", {})
    monkeypatch.setattr(discovery_module, "PROVIDER_ALIASES", {"llama-cli": "llamacpp"})
    monkeypatch.setattr(discovery_module, "PROVIDER_BINARIES", {"llamacpp": ["llama-cli"]})
    monkeypatch.setattr(
        discovery_module.shutil,
        "which",
        lambda tool: "/bin/llama-cli" if tool == "llama-cli" else None,
    )

    detector = ConfigDetector()
    results = detector.discover_cli_tools()

    assert len(results["installed"]) == 1
    assert results["installed"][0]["name"] == "llama-cli"
    assert results["installed"][0]["has_config"] is True
    assert results["installed"][0]["config_path"] == str(model_dir)


def test_config_check_result_is_ready_property() -> None:
    ready_with_config = ConfigCheckResult(provider="codex", has_binary=True, has_config=True)
    ready_with_auth = ConfigCheckResult(provider="codex", has_binary=True, has_auth=True)
    not_ready = ConfigCheckResult(provider="codex", has_binary=False, has_config=True)

    assert ready_with_config.is_ready is True
    assert ready_with_auth.is_ready is True
    assert not_ready.is_ready is False


def test_check_provider_sets_error_on_auth_exception(monkeypatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "codex-config"
    config_dir.mkdir()

    monkeypatch.setattr(discovery_module, "CONFIG_LOCATIONS", {"codex": [str(config_dir)]})
    monkeypatch.setattr(discovery_module, "AUTH_CHECK_COMMANDS", {"codex": ["codex", "--version"]})
    monkeypatch.setattr(
        discovery_module.shutil,
        "which",
        lambda tool: "/bin/codex" if tool == "codex" else None,
    )

    detector = ConfigDetector()

    def _boom(args: list[str], **kwargs: object) -> ExecutorResult:
        _ = (args, kwargs)
        raise RuntimeError("auth command failed")

    detector._executor.run = _boom  # type: ignore[method-assign]

    result = detector.check_provider("codex")

    assert result.has_binary is True
    assert result.auth_status == "error"
    assert any("Auth check failed" in err for err in result.errors)


def test_check_all_returns_entries_for_all_configured_providers(monkeypatch) -> None:
    monkeypatch.setattr(discovery_module, "CONFIG_LOCATIONS", {"a": [], "b": [], "c": []})
    monkeypatch.setattr(discovery_module.shutil, "which", lambda _tool: None)

    detector = ConfigDetector()
    results = detector.check_all()

    assert [r.provider for r in results] == ["a", "b", "c"]


def test_check_available_filters_to_installed_binaries(monkeypatch) -> None:
    monkeypatch.setattr(discovery_module, "CONFIG_LOCATIONS", {"a": [], "b": [], "c": []})
    monkeypatch.setattr(discovery_module, "AUTH_CHECK_COMMANDS", {})
    monkeypatch.setattr(
        discovery_module.shutil,
        "which",
        lambda tool: "/bin/b" if tool == "b" else None,
    )

    detector = ConfigDetector()
    results = detector.check_available()

    assert len(results) == 1
    assert results[0].provider == "b"
    assert results[0].has_binary is True


def test_discover_cli_tools_auth_exception_sets_error_status(monkeypatch) -> None:
    monkeypatch.setattr(discovery_module, "CONFIG_LOCATIONS", {"codex": []})
    monkeypatch.setattr(discovery_module, "AUTH_CHECK_COMMANDS", {"codex": ["codex", "--version"]})
    monkeypatch.setattr(
        discovery_module.shutil,
        "which",
        lambda tool: "/bin/codex" if tool == "codex" else None,
    )

    detector = ConfigDetector()

    def _boom(args: list[str], **kwargs: object) -> ExecutorResult:
        _ = (args, kwargs)
        raise RuntimeError("auth check exploded")

    detector._executor.run = _boom  # type: ignore[method-assign]
    results = detector.discover_cli_tools(check_auth=True)

    codex = next(item for item in results["installed"] if item["name"] == "codex")
    assert codex["auth_status"] == "error"
    assert "auth check exploded" in codex["auth_error"]
    assert results["ready"] == []
