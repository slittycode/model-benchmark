"""Integration tests for CLI commands."""

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from mrbench.adapters.base import AdapterCapabilities, DetectionResult, RunResult
from mrbench.cli import bench as bench_module
from mrbench.cli import detect as detect_module
from mrbench.cli import discover as discover_module
from mrbench.cli import report as report_module
from mrbench.cli.main import app
from mrbench.core.storage import Storage

runner = CliRunner()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences for stable help-text assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestDoctorCommand:
    """Tests for mrbench doctor."""

    def test_doctor_runs(self):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0 or result.exit_code == 1

    def test_doctor_json_output(self):
        result = runner.invoke(app, ["doctor", "--json"])
        # Should return valid JSON even if no providers
        assert "python_version" in result.stdout or result.exit_code == 1


class TestProvidersCommand:
    """Tests for mrbench providers."""

    def test_providers_lists_fake(self):
        result = runner.invoke(app, ["providers"])
        assert result.exit_code == 0
        assert "fake" in result.stdout.lower()


class TestModelsCommand:
    """Tests for mrbench models."""

    def test_models_fake(self):
        result = runner.invoke(app, ["models", "fake"])
        assert result.exit_code == 0
        assert "fake-fast" in result.stdout


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


class TestRouteCommand:
    """Tests for mrbench route."""

    def test_route_finds_provider(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Test prompt")

        result = runner.invoke(app, ["route", "--prompt", str(prompt_file)])
        assert result.exit_code == 0


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

    def test_detect_json_handles_model_listing_failures(self, monkeypatch):
        monkeypatch.setattr(detect_module, "get_default_registry", lambda: self._FakeRegistry())

        result = runner.invoke(app, ["detect", "--json"])
        assert result.exit_code == 0

        payload = json.loads(_strip_ansi(result.stdout))
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

        clean_stdout = re.sub(r"[^\x20-\x7E\n\t]", "", _strip_ansi(result.stdout))
        run_match = re.search(r'"run_id"\s*:\s*"([^"]+)"', clean_stdout)
        output_match = re.search(r'"output_dir"\s*:\s*"([^"]+)"', clean_stdout)
        assert run_match is not None
        assert output_match is not None

        run_id = run_match.group(1)
        run_dir = out_dir / run_id
        output_dir_value = output_match.group(1).replace("\n", "")
        assert output_dir_value == str(run_dir)
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

        payload = json.loads(_strip_ansi(result.stdout))
        assert payload["providers"]["fake"]["avg_ttft_ms"] == 0.0
