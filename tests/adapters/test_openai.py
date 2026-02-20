"""Tests for OpenAI API adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mrbench.adapters.base import RunOptions
from mrbench.adapters.openai import OpenAIAdapter


class TestOpenAIAdapter:
    """Test OpenAI adapter."""

    def test_adapter_name(self):
        adapter = OpenAIAdapter()
        assert adapter.name == "openai"

    def test_adapter_display_name(self):
        adapter = OpenAIAdapter()
        assert adapter.display_name == "OpenAI"

    def test_detect_no_api_key(self):
        adapter = OpenAIAdapter(api_key=None)
        with patch.dict("os.environ", {}, clear=True):
            result = adapter.detect()
        assert result.detected is False
        assert "OPENAI_API_KEY" in result.error

    def test_detect_with_api_key_sdk_not_installed(self):
        adapter = OpenAIAdapter(api_key="sk-test")
        with patch("mrbench.adapters.openai.OpenAIAdapter._get_client") as mock_client:
            mock_client.side_effect = ImportError("No module named 'openai'")
            result = adapter.detect()
        assert result.detected is True
        assert result.auth_status == "error"

    def test_list_models_fallback(self):
        adapter = OpenAIAdapter()
        with patch("mrbench.adapters.openai.OpenAIAdapter._get_client") as mock_client:
            mock_client.side_effect = Exception("fail")
            models = adapter.list_models()
        assert "gpt-4o" in models
        assert "gpt-4o-mini" in models

    def test_run_no_api_key(self):
        adapter = OpenAIAdapter(api_key=None)
        with patch.dict("os.environ", {}, clear=True):
            result = adapter.run("Hello", RunOptions(model="gpt-4o-mini"))
        assert result.exit_code == 1
        assert "OPENAI_API_KEY" in result.error

    def test_run_success(self):
        adapter = OpenAIAdapter(api_key="sk-test")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello, world!"))]

        with patch.object(adapter, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            result = adapter.run("Say hello", RunOptions(model="gpt-4o-mini"))

        assert result.exit_code == 0
        assert result.output == "Hello, world!"
        assert result.wall_time_ms > 0

    def test_run_api_error(self):
        adapter = OpenAIAdapter(api_key="sk-test")

        with patch.object(adapter, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create.side_effect = Exception(
                "Rate limit exceeded"
            )
            result = adapter.run("Hello", RunOptions(model="gpt-4o-mini"))

        assert result.exit_code == 1
        assert "Rate limit exceeded" in result.error

    def test_capabilities(self):
        adapter = OpenAIAdapter()
        caps = adapter.get_capabilities()
        assert caps.name == "openai"
        assert caps.streaming is True
        assert caps.tool_calling is True
        assert caps.offline is False
