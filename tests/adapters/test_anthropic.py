"""Tests for Anthropic API adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mrbench.adapters.anthropic import AnthropicAdapter
from mrbench.adapters.base import RunOptions


class TestAnthropicAdapter:
    """Test Anthropic adapter."""

    def test_adapter_name(self):
        adapter = AnthropicAdapter()
        assert adapter.name == "anthropic"

    def test_adapter_display_name(self):
        adapter = AnthropicAdapter()
        assert adapter.display_name == "Anthropic"

    def test_detect_no_api_key(self):
        adapter = AnthropicAdapter(api_key=None)
        with patch.dict("os.environ", {}, clear=True):
            result = adapter.detect()
        assert result.detected is False
        assert "ANTHROPIC_API_KEY" in result.error

    def test_detect_with_api_key_sdk_not_installed(self):
        adapter = AnthropicAdapter(api_key="sk-ant-test")
        with patch("mrbench.adapters.anthropic.AnthropicAdapter._get_client") as mock_client:
            mock_client.side_effect = ImportError("No module named 'anthropic'")
            result = adapter.detect()
        assert result.detected is True
        assert result.auth_status == "error"

    def test_list_models_returns_defaults(self):
        adapter = AnthropicAdapter()
        models = adapter.list_models()
        assert "claude-sonnet-4-20250514" in models
        assert "claude-3-haiku-20240307" in models

    def test_run_no_api_key(self):
        adapter = AnthropicAdapter(api_key=None)
        with patch.dict("os.environ", {}, clear=True):
            result = adapter.run("Hello", RunOptions(model="claude-3-haiku"))
        assert result.exit_code == 1
        assert "ANTHROPIC_API_KEY" in result.error

    def test_run_success(self):
        adapter = AnthropicAdapter(api_key="sk-ant-test")

        mock_block = MagicMock()
        mock_block.text = "Hello, world!"

        mock_response = MagicMock()
        mock_response.content = [mock_block]

        with patch.object(adapter, "_get_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_response
            result = adapter.run("Say hello", RunOptions(model="claude-3-haiku"))

        assert result.exit_code == 0
        assert result.output == "Hello, world!"
        assert result.wall_time_ms > 0

    def test_run_api_error(self):
        adapter = AnthropicAdapter(api_key="sk-ant-test")

        with patch.object(adapter, "_get_client") as mock_client:
            mock_client.return_value.messages.create.side_effect = Exception("Rate limit exceeded")
            result = adapter.run("Hello", RunOptions(model="claude-3-haiku"))

        assert result.exit_code == 1
        assert "Rate limit exceeded" in result.error

    def test_capabilities(self):
        adapter = AnthropicAdapter()
        caps = adapter.get_capabilities()
        assert caps.name == "anthropic"
        assert caps.streaming is True
        assert caps.tool_calling is True
        assert caps.offline is False
