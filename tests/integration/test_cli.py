"""Integration tests for CLI commands."""

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from typer.testing import CliRunner

from mrbench.adapters.base import AdapterCapabilities, DetectionResult, RunResult
from mrbench.cli import bench as bench_module
from mrbench.cli import detect as detect_module
from mrbench.cli import discover as discover_module
from mrbench.cli import models as models_module
from mrbench.cli import providers as providers_module
from mrbench.cli import report as report_module
from mrbench.cli import route as route_module
from mrbench.cli import run as run_module
from mrbench.cli.main import app
from mrbench.core.storage import Storage

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences for stable help-text assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _parse_json_output(text: str) -> Any:
    """Parse CLI JSON output robustly when terminal wrapping inserts control chars/newlines."""
    clean_text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", "", _strip_ansi(text)).replace("\r", "")

    # Fast path: output is only JSON.
    stripped = clean_text.strip()
    for candidate in (stripped, stripped.replace("\n", "")):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Fallback: extract first object/array blob from wrapped output.
    for open_char, close_char in (("{", "}"), ("[", "]")):
        start_idx = clean_text.find(open_char)
        end_idx = clean_text.rfind(close_char)
        if start_idx == -1 or end_idx == -1:
            continue
        blob = clean_text[start_idx : end_idx + 1]
        for candidate in (blob, blob.replace("\n", "")):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    raise AssertionError("Failed to parse JSON output")


def _parse_raw_json_output(text: str) -> Any:
    """Parse strict raw JSON output without fallback cleanup logic."""
    return json.loads(text)


class TestDoctorCommand:
    """Tests for mrbench doctor."""

    def test_doctor_runs(self):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0 or result.exit_code == 1

    def test_doctor_json_output(self):
        result = runner.invoke(app, ["doctor", "--json"])
        # Should return valid JSON even if no providers
        assert "python_version" in result.stdout or result.exit_code == 1

    def test_doctor_json_output_is_raw_parseable(self):
        result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0
        payload = _parse_raw_json_output(result.stdout)
        assert "python_version" in payload


class TestProvidersCommand:
    """Tests for mrbench providers."""

    def test_providers_lists_fake(self):
        result = runner.invoke(app, ["providers"])
        assert result.exit_code == 0
        assert "fake" in result.stdout.lower()

    def test_providers_json_output_is_raw_parseable_with_long_values(self, monkeypatch):
        class _Adapter:
            name = "fake-provider"
            display_name = "Fake Provider " + ("x" * 120)

            def detect(self) -> DetectionResult:
                return DetectionResult(
                    detected=True,
                    binary_path="/bin/fake-provider",
                    version="v" + ("9" * 160),
                    auth_status="authenticated",
                    trusted=True,
                )

            def get_capabilities(self) -> AdapterCapabilities:
                return AdapterCapabilities(name=self.name, offline=False)

        class _Registry:
            def list_all(self):
                return [_Adapter()]

        monkeypatch.setattr(providers_module, "get_default_registry", lambda: _Registry())
        result = runner.invoke(app, ["providers", "--json"])
        assert result.exit_code == 0
        payload = _parse_raw_json_output(result.stdout)
        assert payload[0]["name"] == "fake-provider"


class TestModelsCommand:
    """Tests for mrbench models."""

    def test_models_fake(self):
        result = runner.invoke(app, ["models", "fake"])
        assert result.exit_code == 0
        assert "fake-fast" in result.stdout

    def test_models_unknown_provider_fails(self, monkeypatch):
        class _Registry:
            def get(self, provider: str):
                _ = provider
                return None

            def get_available(self):
                return []

        monkeypatch.setattr(models_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["models", "missing"])
        assert result.exit_code == 1
        assert "Unknown provider: missing" in _strip_ansi(result.stdout)

    def test_models_provider_not_available_fails(self, monkeypatch):
        class _Adapter:
            def is_available(self) -> bool:
                return False

        class _Registry:
            def get(self, provider: str):
                _ = provider
                return _Adapter()

            def get_available(self):
                return []

        monkeypatch.setattr(models_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["models", "fake"])
        assert result.exit_code == 1
        assert "Provider 'fake' is not available" in _strip_ansi(result.stdout)

    def test_models_provider_list_error_fails(self, monkeypatch):
        class _Adapter:
            def is_available(self) -> bool:
                return True

            def list_models(self):
                raise RuntimeError("list failure")

        class _Registry:
            def get(self, provider: str):
                _ = provider
                return _Adapter()

            def get_available(self):
                return []

        monkeypatch.setattr(models_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["models", "fake"])
        assert result.exit_code == 1
        assert "Error listing models: list failure" in _strip_ansi(result.stdout)

    def test_models_all_json_lists_only_non_empty_models(self, monkeypatch):
        class _AdapterWithModels:
            name = "a"

            def list_models(self) -> list[str]:
                return ["m1", "m2"]

        class _AdapterNoModels:
            name = "b"

            def list_models(self) -> list[str]:
                return []

        class _Registry:
            def get_available(self):
                return [_AdapterWithModels(), _AdapterNoModels()]

            def get(self, provider: str):
                _ = provider
                return None

        monkeypatch.setattr(models_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["models", "--json"])
        assert result.exit_code == 0
        payload = _parse_json_output(result.stdout)
        assert payload == {"a": ["m1", "m2"]}

    def test_models_all_no_models_prints_guidance(self, monkeypatch):
        class _Adapter:
            name = "a"

            def list_models(self) -> list[str]:
                return []

        class _Registry:
            def get_available(self):
                return [_Adapter()]

            def get(self, provider: str):
                _ = provider
                return None

        monkeypatch.setattr(models_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["models"])
        assert result.exit_code == 0
        assert "No models found. Ensure providers are running." in _strip_ansi(result.stdout)

    def test_models_all_handles_adapter_list_exception(self, monkeypatch):
        class _AdapterBroken:
            name = "broken"

            def list_models(self) -> list[str]:
                raise RuntimeError("adapter failure")

        class _Registry:
            def get_available(self):
                return [_AdapterBroken()]

            def get(self, provider: str):
                _ = provider
                return None

        monkeypatch.setattr(models_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["models"])
        assert result.exit_code == 0
        assert "No models found. Ensure providers are running." in _strip_ansi(result.stdout)

    def test_models_all_prints_non_json_grouped_output(self, monkeypatch):
        class _Adapter:
            name = "provider-a"

            def list_models(self) -> list[str]:
                return ["m1", "m2"]

        class _Registry:
            def get_available(self):
                return [_Adapter()]

            def get(self, provider: str):
                _ = provider
                return None

        monkeypatch.setattr(models_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["models"])
        assert result.exit_code == 0
        output = _strip_ansi(result.stdout)
        assert "provider-a" in output
        assert "m1" in output
        assert "m2" in output

    def test_models_specific_json_output(self, monkeypatch):
        class _Adapter:
            def is_available(self) -> bool:
                return True

            def list_models(self) -> list[str]:
                return ["x", "y"]

        class _Registry:
            def get(self, provider: str):
                _ = provider
                return _Adapter()

            def get_available(self):
                return []

        monkeypatch.setattr(models_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["models", "fake", "--json"])
        assert result.exit_code == 0
        payload = _parse_json_output(result.stdout)
        assert payload == ["x", "y"]

    def test_models_specific_no_models_prints_guidance(self, monkeypatch):
        class _Adapter:
            def is_available(self) -> bool:
                return True

            def list_models(self) -> list[str]:
                return []

        class _Registry:
            def get(self, provider: str):
                _ = provider
                return _Adapter()

            def get_available(self):
                return []

        monkeypatch.setattr(models_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["models", "fake"])
        assert result.exit_code == 0
        output = _strip_ansi(result.stdout)
        assert "No models available for fake." in output
        assert "specify a model ID manually" in output

    def test_models_json_output_is_raw_parseable_with_long_values(self, monkeypatch):
        class _Adapter:
            name = "provider-a"

            def list_models(self) -> list[str]:
                return ["model-" + ("m" * 200)]

        class _Registry:
            def get_available(self):
                return [_Adapter()]

            def get(self, provider: str):
                _ = provider
                return None

        monkeypatch.setattr(models_module, "get_default_registry", lambda: _Registry())
        result = runner.invoke(app, ["models", "--json"])
        assert result.exit_code == 0
        payload = _parse_raw_json_output(result.stdout)
        assert "provider-a" in payload


class TestRunCommand:
    """Tests for mrbench run."""

    def test_run_fake_provider(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Hello")

        result = runner.invoke(
            app, ["run", "-p", "fake", "-m", "fake-fast", "--prompt", str(prompt_file)]
        )
        assert result.exit_code == 0
        assert "Fake response" in result.stdout

    def test_run_unknown_provider_shows_available(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Hello")

        class _FakeRegistry:
            def get(self, provider: str):
                _ = provider
                return None

            def list_names(self) -> list[str]:
                return ["fake", "codex"]

        monkeypatch.setattr(run_module, "get_default_registry", lambda: _FakeRegistry())

        result = runner.invoke(
            app, ["run", "-p", "missing", "-m", "fake-fast", "--prompt", str(prompt_file)]
        )
        assert result.exit_code == 1
        output = _strip_ansi(result.stdout)
        assert "Unknown provider: missing" in output
        assert "Available: fake, codex" in output

    def test_run_provider_not_available(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Hello")

        class _UnavailableAdapter:
            def is_available(self) -> bool:
                return False

        class _FakeRegistry:
            def get(self, provider: str):
                _ = provider
                return _UnavailableAdapter()

            def list_names(self) -> list[str]:
                return ["fake"]

        monkeypatch.setattr(run_module, "get_default_registry", lambda: _FakeRegistry())

        result = runner.invoke(
            app, ["run", "-p", "fake", "-m", "fake-fast", "--prompt", str(prompt_file)]
        )
        assert result.exit_code == 1
        assert "Provider 'fake' is not available" in _strip_ansi(result.stdout)

    def test_run_empty_prompt_fails(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text(" \n")

        result = runner.invoke(
            app, ["run", "-p", "fake", "-m", "fake-fast", "--prompt", str(prompt_file)]
        )
        assert result.exit_code == 1
        assert "Empty prompt" in _strip_ansi(result.stdout)

    def test_run_handles_adapter_exception(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Hello")

        class _BrokenAdapter:
            def is_available(self) -> bool:
                return True

            def run(self, prompt: str, options: object):
                _ = (prompt, options)
                raise RuntimeError("boom")

        class _FakeRegistry:
            def get(self, provider: str):
                _ = provider
                return _BrokenAdapter()

            def list_names(self) -> list[str]:
                return ["fake"]

        monkeypatch.setattr(run_module, "get_default_registry", lambda: _FakeRegistry())

        result = runner.invoke(
            app, ["run", "-p", "fake", "-m", "fake-fast", "--prompt", str(prompt_file)]
        )
        assert result.exit_code == 1
        assert "Error running prompt: boom" in _strip_ansi(result.stdout)

    def test_run_json_nonzero_exit_redacts_error(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Hello")

        class _Adapter:
            def is_available(self) -> bool:
                return True

            def run(self, prompt: str, options: object) -> RunResult:
                _ = (prompt, options)
                return RunResult(
                    output="failure output",
                    exit_code=7,
                    wall_time_ms=3.5,
                    error="upstream auth failed with key sk-abcdefghijklmnopqrstuv",
                )

        class _Registry:
            def get(self, provider: str):
                _ = provider
                return _Adapter()

            def list_names(self) -> list[str]:
                return ["fake"]

        monkeypatch.setattr(run_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(
            app, ["run", "-p", "fake", "-m", "fake-fast", "--prompt", str(prompt_file), "--json"]
        )
        assert result.exit_code == 7
        payload = _parse_json_output(result.stdout)
        assert payload["exit_code"] == 7
        assert payload["error"] is not None
        assert "sk-abcdefghijklmnopqrstuv" not in payload["error"]
        assert "[REDACTED]" in payload["error"]

    def test_run_json_output_is_raw_parseable_with_long_values(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Hello")

        class _Adapter:
            def is_available(self) -> bool:
                return True

            def run(self, prompt: str, options: object) -> RunResult:
                _ = (prompt, options)
                return RunResult(
                    output="out-" + ("z" * 220),
                    exit_code=0,
                    wall_time_ms=3.5,
                )

        class _Registry:
            def get(self, provider: str):
                _ = provider
                return _Adapter()

            def list_names(self) -> list[str]:
                return ["fake"]

        monkeypatch.setattr(run_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(
            app, ["run", "-p", "fake", "-m", "fake-fast", "--prompt", str(prompt_file), "--json"]
        )
        assert result.exit_code == 0
        payload = _parse_raw_json_output(result.stdout)
        assert payload["output"].startswith("out-")

    def test_run_non_json_nonzero_exit_prints_redacted_error(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Hello")

        class _Adapter:
            def is_available(self) -> bool:
                return True

            def run(self, prompt: str, options: object) -> RunResult:
                _ = (prompt, options)
                return RunResult(
                    output="",
                    exit_code=9,
                    wall_time_ms=3.5,
                    error="bad token sk-abcdefghijklmnopqrstuv",
                )

        class _Registry:
            def get(self, provider: str):
                _ = provider
                return _Adapter()

            def list_names(self) -> list[str]:
                return ["fake"]

        monkeypatch.setattr(run_module, "get_default_registry", lambda: _Registry())
        result = runner.invoke(
            app, ["run", "-p", "fake", "-m", "fake-fast", "--prompt", str(prompt_file)]
        )
        assert result.exit_code == 9
        output = _strip_ansi(result.stdout)
        assert "[REDACTED]" in output
        assert "sk-abcdefghijklmnopqrstuv" not in output


class TestRouteCommand:
    """Tests for mrbench route."""

    def test_route_finds_provider(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Test prompt")

        result = runner.invoke(app, ["route", "--prompt", str(prompt_file)])
        assert result.exit_code == 0

    def test_route_missing_prompt_file_fails(self, tmp_path):
        missing = tmp_path / "missing.txt"
        result = runner.invoke(app, ["route", "--prompt", str(missing)])
        assert result.exit_code == 1
        assert "Prompt file not found" in _strip_ansi(result.stdout)

    def test_route_fails_when_no_providers_available(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Test prompt")

        class _EmptyRegistry:
            def get_available(self):
                return []

        monkeypatch.setattr(route_module, "get_default_registry", lambda: _EmptyRegistry())
        monkeypatch.setattr(
            route_module,
            "load_config",
            lambda: SimpleNamespace(routing=SimpleNamespace(preference_order=[]), providers={}),
        )

        result = runner.invoke(app, ["route", "--prompt", str(prompt_file)])
        assert result.exit_code == 1
        assert "No providers available" in _strip_ansi(result.stdout)

    def test_route_fails_when_constraints_filter_all_candidates(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Test prompt")

        class _Adapter:
            name = "fake"

            def get_capabilities(self) -> AdapterCapabilities:
                return AdapterCapabilities(name=self.name, offline=False, streaming=False)

        class _Registry:
            def get_available(self):
                return [_Adapter()]

        monkeypatch.setattr(route_module, "get_default_registry", lambda: _Registry())
        monkeypatch.setattr(
            route_module,
            "load_config",
            lambda: SimpleNamespace(
                routing=SimpleNamespace(preference_order=["fake"]),
                providers={},
            ),
        )

        result = runner.invoke(app, ["route", "--prompt", str(prompt_file), "--offline-only"])
        assert result.exit_code == 1
        assert "No providers match the constraints" in _strip_ansi(result.stdout)

    def test_route_json_explain_uses_config_default_model(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Test prompt")

        class _Adapter:
            name = "fake"

            def get_capabilities(self) -> AdapterCapabilities:
                return AdapterCapabilities(name=self.name, offline=True, streaming=True)

            def list_models(self) -> list[str]:
                return ["fallback-model"]

        class _Registry:
            def get_available(self):
                return [_Adapter()]

        monkeypatch.setattr(route_module, "get_default_registry", lambda: _Registry())
        monkeypatch.setattr(
            route_module,
            "load_config",
            lambda: SimpleNamespace(
                routing=SimpleNamespace(preference_order=["fake"]),
                providers={"fake": SimpleNamespace(default_model="cfg-model")},
            ),
        )

        result = runner.invoke(
            app,
            [
                "route",
                "--prompt",
                str(prompt_file),
                "--json",
                "--explain",
                "--offline-only",
                "--streaming-required",
            ],
        )
        assert result.exit_code == 0
        payload = _parse_json_output(result.stdout)
        assert payload["provider"] == "fake"
        assert payload["model"] == "cfg-model"
        assert payload["offline"] is True
        assert payload["streaming"] is True
        assert any("preference order" in reason for reason in payload["explanation"])

    def test_route_json_output_is_raw_parseable_with_long_values(self, monkeypatch, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Test prompt")

        class _Adapter:
            name = "fake"

            def get_capabilities(self) -> AdapterCapabilities:
                return AdapterCapabilities(name=self.name, offline=True, streaming=True)

            def list_models(self) -> list[str]:
                return ["model-" + ("q" * 210)]

        class _Registry:
            def get_available(self):
                return [_Adapter()]

        monkeypatch.setattr(route_module, "get_default_registry", lambda: _Registry())
        monkeypatch.setattr(
            route_module,
            "load_config",
            lambda: SimpleNamespace(
                routing=SimpleNamespace(preference_order=["fake"]), providers={}
            ),
        )

        result = runner.invoke(app, ["route", "--prompt", str(prompt_file), "--json", "--explain"])
        assert result.exit_code == 0
        payload = _parse_raw_json_output(result.stdout)
        assert payload["provider"] == "fake"


class TestDiscoverCommand:
    """Tests for mrbench discover."""

    def test_discover_json_check_auth_flag(self, monkeypatch):
        calls: list[bool] = []

        class _FakeDetector:
            def discover_cli_tools(self, check_auth: bool = False):
                calls.append(check_auth)
                return {
                    "installed": [
                        {
                            "name": "codex",
                            "path": "/bin/codex",
                            "has_config": False,
                            "config_path": None,
                            "auth_status": "authenticated",
                        }
                    ],
                    "configured": [],
                    "ready": [],
                    "not_found": [],
                }

        monkeypatch.setattr(discover_module, "ConfigDetector", lambda: _FakeDetector())

        result = runner.invoke(app, ["discover", "--json", "--check-auth"])
        assert result.exit_code == 0
        assert calls == [True]

        payload = json.loads(_strip_ansi(result.stdout))
        assert payload["installed"][0]["name"] == "codex"

    def test_discover_json_output_is_raw_parseable_with_long_values(self, monkeypatch):
        class _FakeDetector:
            def discover_cli_tools(self, check_auth: bool = False):
                _ = check_auth
                return {
                    "installed": [
                        {
                            "name": "codex",
                            "path": "/bin/" + ("c" * 180),
                            "has_config": True,
                            "config_path": "/tmp/" + ("cfg" * 60),
                            "auth_status": "authenticated",
                        }
                    ],
                    "configured": [{"name": "codex"}],
                    "ready": [{"name": "codex"}],
                    "not_found": [],
                }

        monkeypatch.setattr(discover_module, "ConfigDetector", lambda: _FakeDetector())

        result = runner.invoke(app, ["discover", "--json"])
        assert result.exit_code == 0
        payload = _parse_raw_json_output(result.stdout)
        assert payload["installed"][0]["name"] == "codex"

    def test_discover_rich_all_and_auth_statuses(self, monkeypatch):
        class _FakeDetector:
            def discover_cli_tools(self, check_auth: bool = False):
                assert check_auth is True
                return {
                    "installed": [
                        {
                            "name": "codex",
                            "path": "/bin/codex",
                            "has_config": True,
                            "config_path": "/tmp/codex-config",
                            "auth_status": "authenticated",
                        },
                        {
                            "name": "goose",
                            "path": "/bin/goose",
                            "has_config": False,
                            "config_path": None,
                            "auth_status": "not_authenticated",
                        },
                        {
                            "name": "opencode",
                            "path": "/bin/opencode",
                            "has_config": False,
                            "config_path": None,
                            "auth_status": "error",
                            "auth_error": "login failed",
                        },
                        {
                            "name": "gemini",
                            "path": "/bin/gemini",
                            "has_config": False,
                            "config_path": None,
                        },
                    ],
                    "configured": [{"name": "codex"}],
                    "ready": [{"name": "codex"}],
                    "not_found": ["claude", "ollama"],
                }

        monkeypatch.setattr(discover_module, "ConfigDetector", lambda: _FakeDetector())

        result = runner.invoke(app, ["discover", "--all", "--check-auth"])
        assert result.exit_code == 0
        output = _strip_ansi(result.stdout)
        assert "AI CLI Tool Discovery" in output
        assert "Not installed:" in output
        assert "claude" in output
        assert "ollama" in output
        assert "Auth Check Results:" in output
        assert "codex: authenticated" in output
        assert "goose: not authenticated" in output
        assert "opencode: login failed" in output
        assert "gemini: not checked" in output

    def test_discover_does_not_print_auth_section_without_check_auth(self, monkeypatch):
        class _FakeDetector:
            def discover_cli_tools(self, check_auth: bool = False):
                assert check_auth is False
                return {
                    "installed": [
                        {
                            "name": "codex",
                            "path": "/bin/codex",
                            "has_config": False,
                            "config_path": None,
                        }
                    ],
                    "configured": [],
                    "ready": [],
                    "not_found": [],
                }

        monkeypatch.setattr(discover_module, "ConfigDetector", lambda: _FakeDetector())

        result = runner.invoke(app, ["discover"])
        assert result.exit_code == 0
        output = _strip_ansi(result.stdout)
        assert "AI CLI Tool Discovery" in output
        assert "Auth Check Results:" not in output


class TestDetectCommand:
    """Tests for mrbench detect."""

    class _FakeAdapter:
        name = "fake-provider"
        display_name = "Fake Provider"

        def detect(self) -> DetectionResult:
            return DetectionResult(
                detected=True,
                binary_path="/bin/fake-provider",
                version="1.2.3",
                auth_status="authenticated",
                trusted=True,
            )

        def list_models(self) -> list[str]:
            raise RuntimeError("no model listing")

        def get_capabilities(self) -> AdapterCapabilities:
            return AdapterCapabilities(
                name=self.name,
                streaming=True,
                tool_calling=False,
                max_tokens=4096,
                max_context=32768,
                offline=False,
            )

    class _FakeRegistry:
        def list_all(self):
            return [TestDetectCommand._FakeAdapter()]

    def test_detect_summary_skips_undetected_and_prints_no_model_list(self, monkeypatch):
        class _UndetectedAdapter:
            name = "missing-provider"
            display_name = "Missing Provider"

            def detect(self) -> DetectionResult:
                return DetectionResult(detected=False)

            def list_models(self) -> list[str]:
                return ["should-not-appear"]

            def get_capabilities(self) -> AdapterCapabilities:
                return AdapterCapabilities(name=self.name)

        class _DetectedNoModelsAdapter:
            name = "detected-provider"
            display_name = "Detected Provider"

            def detect(self) -> DetectionResult:
                return DetectionResult(
                    detected=True,
                    binary_path="/bin/detected-provider",
                    version="1.0.0",
                    auth_status="authenticated",
                    trusted=True,
                )

            def list_models(self) -> list[str]:
                return []

            def get_capabilities(self) -> AdapterCapabilities:
                return AdapterCapabilities(
                    name=self.name,
                    streaming=False,
                    tool_calling=False,
                    offline=True,
                )

        class _Registry:
            def list_all(self):
                return [_UndetectedAdapter(), _DetectedNoModelsAdapter()]

        monkeypatch.setattr(detect_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["detect"])
        assert result.exit_code == 0
        output = _strip_ansi(result.stdout)
        assert "Detected 1 providers" in output
        assert "Detected Provider" in output
        assert "no model list" in output
        assert "Missing Provider" not in output

    def test_detect_json_handles_model_listing_failures(self, monkeypatch):
        monkeypatch.setattr(detect_module, "get_default_registry", lambda: self._FakeRegistry())

        result = runner.invoke(app, ["detect", "--json"])
        assert result.exit_code == 0

        payload = _parse_json_output(result.stdout)
        assert len(payload["providers"]) == 1
        assert payload["providers"][0]["name"] == "fake-provider"
        assert payload["providers"][0]["models"] == []

    def test_detect_write_outputs_capabilities_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detect_module, "get_default_registry", lambda: self._FakeRegistry())

        result = runner.invoke(app, ["detect", "--write", "--output-dir", str(tmp_path)])
        assert result.exit_code == 0

        cache_file = tmp_path / "capabilities.json"
        assert cache_file.exists()

        payload = json.loads(cache_file.read_text())
        assert len(payload["providers"]) == 1
        assert payload["providers"][0]["display_name"] == "Fake Provider"

    def test_detect_json_output_is_raw_parseable_with_long_values(self, monkeypatch):
        class _LongAdapter(self._FakeAdapter):
            def list_models(self) -> list[str]:
                return ["model-" + ("x" * 220)]

        class _Registry:
            def list_all(self):
                return [_LongAdapter()]

        monkeypatch.setattr(detect_module, "get_default_registry", lambda: _Registry())

        result = runner.invoke(app, ["detect", "--json"])
        assert result.exit_code == 0
        payload = _parse_raw_json_output(result.stdout)
        assert payload["providers"][0]["name"] == "fake-provider"


class TestBenchCommand:
    """Tests for mrbench bench."""

    class _FakeAdapter:
        name = "fake-provider"
        display_name = "Fake Provider"

        def is_available(self) -> bool:
            return True

        def list_models(self) -> list[str]:
            return ["fake-model"]

        def get_capabilities(self) -> AdapterCapabilities:
            return AdapterCapabilities(name=self.name, streaming=False, tool_calling=False)

        def run(self, prompt: str, options: object) -> RunResult:
            _ = options
            return RunResult(
                output=f"response:{prompt}",
                exit_code=0,
                wall_time_ms=12.5,
                ttft_ms=0.0,
                token_count_output=len(prompt),
            )

    class _FakeRegistry:
        def __init__(self, adapter: object) -> None:
            self._adapter = adapter

        def get(self, provider: str):
            if provider == "fake-provider":
                return self._adapter
            return None

        def get_available(self):
            return [self._adapter]

    def _write_suite(self, tmp_path: Path) -> Path:
        suite_path = tmp_path / "suite.yaml"
        suite_path.write_text(
            """
name: Demo Suite
prompts:
  - id: p1
    text: hello
  - id: p2
    text: world
""".strip()
        )
        return suite_path

    def test_bench_json_writes_run_artifacts(self, monkeypatch, tmp_path):
        suite_path = self._write_suite(tmp_path)
        out_dir = tmp_path / "out"
        db_path = tmp_path / "bench.db"

        registry = self._FakeRegistry(self._FakeAdapter())
        monkeypatch.setattr(bench_module, "get_default_registry", lambda: registry)
        monkeypatch.setattr(bench_module, "Storage", lambda: Storage(db_path))

        result = runner.invoke(
            app,
            [
                "bench",
                "--suite",
                str(suite_path),
                "--provider",
                "fake-provider",
                "--output-dir",
                str(out_dir),
                "--store-prompts",
                "--json",
            ],
        )
        assert result.exit_code == 0

        payload = _parse_json_output(result.stdout)
        run_id = payload["run_id"]
        run_dir = out_dir / run_id
        assert payload["output_dir"] == str(run_dir)
        assert run_dir.exists()

        run_meta = json.loads((run_dir / "run_meta.json").read_text())
        assert len(run_meta["jobs"]) == 2

        first_job_id = run_meta["jobs"][0]["job_id"]
        assert (run_dir / "jobs" / f"{first_job_id}.json").exists()
        assert (run_dir / "jobs" / f"{first_job_id}.output.txt").exists()
        assert (run_dir / "jobs" / f"{first_job_id}.prompt.txt").exists()

        with Storage(db_path) as storage:
            run = storage.get_run(run_id)
            assert run is not None
            assert run.status == "completed"
            jobs = storage.get_jobs_for_run(run_id)
            assert len(jobs) == 2

    def test_bench_json_output_is_raw_parseable_with_long_output_dir(self, monkeypatch, tmp_path):
        suite_path = self._write_suite(tmp_path)
        long_out_dir = tmp_path / ("out-" + ("x" * 140))
        db_path = tmp_path / "bench.db"

        registry = self._FakeRegistry(self._FakeAdapter())
        monkeypatch.setattr(bench_module, "get_default_registry", lambda: registry)
        monkeypatch.setattr(bench_module, "Storage", lambda: Storage(db_path))

        result = runner.invoke(
            app,
            [
                "bench",
                "--suite",
                str(suite_path),
                "--provider",
                "fake-provider",
                "--output-dir",
                str(long_out_dir),
                "--json",
            ],
        )
        assert result.exit_code == 0
        payload = _parse_raw_json_output(result.stdout)
        assert "run_id" in payload

    def test_bench_without_store_prompts_keeps_prompt_preview_null(self, monkeypatch, tmp_path):
        suite_path = tmp_path / "suite.yaml"
        suite_path.write_text(
            """
name: Privacy Suite
prompts:
  - id: p1
    text: "api_key=sk-abcdefghijklmnopqrstuv"
""".strip()
        )
        out_dir = tmp_path / "out"
        db_path = tmp_path / "bench.db"

        registry = self._FakeRegistry(self._FakeAdapter())
        monkeypatch.setattr(bench_module, "get_default_registry", lambda: registry)
        monkeypatch.setattr(bench_module, "Storage", lambda: Storage(db_path))

        result = runner.invoke(
            app,
            [
                "bench",
                "--suite",
                str(suite_path),
                "--provider",
                "fake-provider",
                "--output-dir",
                str(out_dir),
                "--json",
            ],
        )
        assert result.exit_code == 0
        run_id = _parse_json_output(result.stdout)["run_id"]

        with Storage(db_path) as storage:
            jobs = storage.get_jobs_for_run(run_id)
            assert len(jobs) == 1
            assert jobs[0].prompt_preview is None

    def test_bench_store_prompts_redacts_prompt_preview(self, monkeypatch, tmp_path):
        suite_path = tmp_path / "suite.yaml"
        suite_path.write_text(
            """
name: Privacy Suite
prompts:
  - id: p1
    text: "api_key=sk-abcdefghijklmnopqrstuv"
""".strip()
        )
        out_dir = tmp_path / "out"
        db_path = tmp_path / "bench.db"

        registry = self._FakeRegistry(self._FakeAdapter())
        monkeypatch.setattr(bench_module, "get_default_registry", lambda: registry)
        monkeypatch.setattr(bench_module, "Storage", lambda: Storage(db_path))

        result = runner.invoke(
            app,
            [
                "bench",
                "--suite",
                str(suite_path),
                "--provider",
                "fake-provider",
                "--output-dir",
                str(out_dir),
                "--store-prompts",
                "--json",
            ],
        )
        assert result.exit_code == 0
        run_id = _parse_json_output(result.stdout)["run_id"]

        with Storage(db_path) as storage:
            jobs = storage.get_jobs_for_run(run_id)
            assert len(jobs) == 1
            assert jobs[0].prompt_preview is not None
            assert "[REDACTED]" in jobs[0].prompt_preview
            assert "sk-abcdefghijklmnopqrstuv" not in jobs[0].prompt_preview

    def test_bench_fails_for_missing_suite(self, tmp_path):
        missing_suite = tmp_path / "does-not-exist.yaml"
        result = runner.invoke(app, ["bench", "--suite", str(missing_suite)])
        assert result.exit_code == 1
        assert "Suite file not found" in _strip_ansi(result.stdout)

    def test_bench_fails_when_provider_unavailable(self, monkeypatch, tmp_path):
        suite_path = self._write_suite(tmp_path)

        class _UnavailableRegistry:
            def get(self, provider: str):
                _ = provider
                return None

            def get_available(self):
                return []

        monkeypatch.setattr(bench_module, "get_default_registry", lambda: _UnavailableRegistry())

        result = runner.invoke(
            app,
            [
                "bench",
                "--suite",
                str(suite_path),
                "--provider",
                "fake-provider",
            ],
        )
        assert result.exit_code == 1
        assert "Provider not available" in _strip_ansi(result.stdout)

    def test_bench_fails_for_malformed_suite_root(self, tmp_path):
        suite_path = tmp_path / "suite.yaml"
        suite_path.write_text("- one\n- two\n")
        result = runner.invoke(app, ["bench", "--suite", str(suite_path)])
        assert result.exit_code == 1
        assert "Invalid suite format" in _strip_ansi(result.stdout)

    def test_bench_fails_for_missing_prompts_key(self, tmp_path):
        suite_path = tmp_path / "suite.yaml"
        suite_path.write_text("name: Missing Prompts\n")
        result = runner.invoke(app, ["bench", "--suite", str(suite_path)])
        assert result.exit_code == 1
        assert "No prompts in suite" in _strip_ansi(result.stdout)

    def test_bench_fails_for_non_mapping_prompt_entry(self, tmp_path):
        suite_path = tmp_path / "suite.yaml"
        suite_path.write_text(
            """
name: Invalid Prompt Entry
prompts:
  - 123
""".strip()
        )
        result = runner.invoke(app, ["bench", "--suite", str(suite_path)])
        assert result.exit_code == 1
        assert "Invalid prompt entry" in _strip_ansi(result.stdout)

    def test_bench_fails_for_empty_prompt_text(self, tmp_path):
        suite_path = tmp_path / "suite.yaml"
        suite_path.write_text(
            """
name: Empty Prompt
prompts:
  - id: p1
    text: "   "
""".strip()
        )
        result = runner.invoke(app, ["bench", "--suite", str(suite_path)])
        assert result.exit_code == 1
        assert "Prompt text cannot be empty" in _strip_ansi(result.stdout)


class TestHelpMessages:
    """Tests for help output."""

    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "doctor" in _strip_ansi(result.stdout)

    def test_run_help(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--provider" in _strip_ansi(result.stdout)


class TestReportCommand:
    """Tests for mrbench report."""

    def test_report_json_preserves_zero_ttft_metric(self, monkeypatch, tmp_path):
        db_path = tmp_path / "report.db"
        storage = Storage(db_path)

        run = storage.create_run(suite_path="suites/basic.yaml")
        job = storage.create_job(
            run_id=run.id,
            provider="fake",
            model="fake-fast",
            prompt_hash="abc123",
        )
        storage.start_job(job.id)
        storage.complete_job(job.id, exit_code=0)
        storage.add_metric(job.id, "wall_time_ms", 12.5, "ms")
        storage.add_metric(job.id, "ttft_ms", 0.0, "ms")
        storage.complete_run(run.id)

        monkeypatch.setattr(report_module, "Storage", lambda: storage)

        result = runner.invoke(app, ["report", run.id, "--format", "json"])
        assert result.exit_code == 0

        payload = _parse_json_output(result.stdout)
        assert payload["providers"]["fake"]["avg_ttft_ms"] == 0.0

    def test_report_json_output_is_raw_parseable_with_long_provider_keys(
        self, monkeypatch, tmp_path
    ):
        db_path = tmp_path / "report.db"
        storage = Storage(db_path)
        provider_name = "provider-" + ("z" * 140)

        run = storage.create_run(suite_path="suites/basic.yaml")
        job = storage.create_job(
            run_id=run.id,
            provider=provider_name,
            model="fake-fast",
            prompt_hash="abc123",
        )
        storage.start_job(job.id)
        storage.complete_job(job.id, exit_code=0)
        storage.add_metric(job.id, "wall_time_ms", 12.5, "ms")
        storage.complete_run(run.id)

        monkeypatch.setattr(report_module, "Storage", lambda: storage)

        result = runner.invoke(app, ["report", run.id, "--format", "json"])
        assert result.exit_code == 0
        payload = _parse_raw_json_output(result.stdout)
        assert provider_name in payload["providers"]

    def test_report_fails_when_run_not_found(self, monkeypatch, tmp_path):
        db_path = tmp_path / "report.db"
        storage = Storage(db_path)

        monkeypatch.setattr(report_module, "Storage", lambda: storage)

        result = runner.invoke(app, ["report", "missing-run-id"])
        assert result.exit_code == 1
        assert "Run not found: missing-run-id" in _strip_ansi(result.stdout)

    def test_report_fails_when_run_has_no_jobs(self, monkeypatch, tmp_path):
        db_path = tmp_path / "report.db"
        storage = Storage(db_path)
        run = storage.create_run(suite_path="suites/basic.yaml")

        monkeypatch.setattr(report_module, "Storage", lambda: storage)

        result = runner.invoke(app, ["report", run.id])
        assert result.exit_code == 1
        assert "No jobs found for this run" in _strip_ansi(result.stdout)

    def test_report_markdown_writes_file_when_run_directory_exists(self, monkeypatch, tmp_path):
        db_path = tmp_path / "report.db"
        storage = Storage(db_path)

        run = storage.create_run(suite_path="suites/basic.yaml")
        job = storage.create_job(
            run_id=run.id,
            provider="fake",
            model="fake-fast",
            prompt_hash="abc123",
        )
        storage.start_job(job.id)
        storage.complete_job(job.id, exit_code=0)
        storage.add_metric(job.id, "wall_time_ms", 12.5, "ms")
        storage.complete_run(run.id)

        output_dir = tmp_path / "out"
        run_dir = output_dir / run.id
        run_dir.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(report_module, "Storage", lambda: storage)

        result = runner.invoke(app, ["report", run.id, "--output-dir", str(output_dir)])
        assert result.exit_code == 0
        output = _strip_ansi(result.stdout).replace("\n", "")
        report_file = run_dir / "report.md"
        assert report_file.exists()
        assert f"Report written to {report_file}" in output
        assert "## Summary" in report_file.read_text()

    def test_report_markdown_prints_when_run_directory_missing(self, monkeypatch, tmp_path):
        db_path = tmp_path / "report.db"
        storage = Storage(db_path)

        run = storage.create_run(suite_path="suites/basic.yaml")
        job = storage.create_job(
            run_id=run.id,
            provider="fake",
            model="fake-fast",
            prompt_hash="abc123",
        )
        storage.start_job(job.id)
        storage.complete_job(job.id, exit_code=0)
        storage.add_metric(job.id, "wall_time_ms", 12.5, "ms")
        storage.complete_run(run.id)

        output_dir = tmp_path / "missing-out-dir"

        monkeypatch.setattr(report_module, "Storage", lambda: storage)

        result = runner.invoke(app, ["report", run.id, "--output-dir", str(output_dir)])
        assert result.exit_code == 0
        output = _strip_ansi(result.stdout)
        assert "# Benchmark Report:" in output
        assert "Generated by mrbench" in output
