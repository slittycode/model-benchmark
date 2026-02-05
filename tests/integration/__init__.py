"""Integration tests for CLI commands."""

import pytest
from typer.testing import CliRunner

from mrbench.cli.main import app

runner = CliRunner()


class TestDoctorCommand:
    """Tests for mrbench doctor."""

    def test_doctor_runs(self):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0 or result.exit_code == 1  # May fail if no providers

    def test_doctor_json_output(self):
        result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0 or result.exit_code == 1
        if result.exit_code == 0:
            assert "python_version" in result.stdout


class TestProvidersCommand:
    """Tests for mrbench providers."""

    def test_providers_lists_all(self):
        result = runner.invoke(app, ["providers"])
        assert result.exit_code == 0
        # Should list at least fake adapter
        assert "fake" in result.stdout.lower()

    def test_providers_json_output(self):
        result = runner.invoke(app, ["providers", "--json"])
        assert result.exit_code == 0
        assert "[" in result.stdout  # JSON array


class TestModelsCommand:
    """Tests for mrbench models."""

    def test_models_fake_provider(self):
        result = runner.invoke(app, ["models", "fake"])
        assert result.exit_code == 0
        assert "fake-fast" in result.stdout


class TestRunCommand:
    """Tests for mrbench run."""

    def test_run_with_fake_provider(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Hello world")

        result = runner.invoke(
            app, ["run", "--provider", "fake", "--model", "fake-fast", "--prompt", str(prompt_file)]
        )
        assert result.exit_code == 0
        assert "Fake response" in result.stdout

    def test_run_json_output(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("Test")

        result = runner.invoke(
            app,
            [
                "run",
                "--provider", "fake",
                "--model", "fake-fast",
                "--prompt", str(prompt_file),
                "--json",
            ],
        )
        assert result.exit_code == 0
        assert '"provider": "fake"' in result.stdout


class TestRouteCommand:
    """Tests for mrbench route."""

    def test_route_finds_provider(self):
        result = runner.invoke(app, ["route"])
        assert result.exit_code == 0
        # Should route to some provider
        assert "Provider:" in result.stdout or "provider" in result.stdout.lower()


class TestHelpMessages:
    """Tests for help messages."""

    def test_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "doctor" in result.stdout
        assert "run" in result.stdout

    def test_run_help(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--provider" in result.stdout
        assert "--model" in result.stdout

    def test_bench_help(self):
        result = runner.invoke(app, ["bench", "--help"])
        assert result.exit_code == 0
        assert "--suite" in result.stdout
