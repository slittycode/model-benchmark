"""Integration tests for CLI commands."""

import pytest
from typer.testing import CliRunner

from mrbench.cli.main import app

runner = CliRunner()


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
        assert "doctor" in result.stdout

    def test_run_help(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--provider" in result.stdout
