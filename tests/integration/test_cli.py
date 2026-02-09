"""Integration tests for CLI commands."""

import json
import re

from typer.testing import CliRunner

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
