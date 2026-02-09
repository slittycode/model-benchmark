"""Tests for discovery behavior."""

from __future__ import annotations

from pathlib import Path

from mrbench.core import discovery as discovery_module
from mrbench.core.discovery import ConfigDetector
from mrbench.core.executor import ExecutorResult


def test_discover_cli_tools_skips_auth_checks_by_default(
    monkeypatch, tmp_path: Path
) -> None:
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


def test_discover_cli_tools_runs_auth_checks_when_enabled(
    monkeypatch, tmp_path: Path
) -> None:
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
    monkeypatch.setattr(discovery_module, "AUTH_CHECK_COMMANDS", {"azure": ["az", "account", "show"]})
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
    monkeypatch.setattr(discovery_module, "AUTH_CHECK_COMMANDS", {"azure": ["az", "account", "show"]})
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
