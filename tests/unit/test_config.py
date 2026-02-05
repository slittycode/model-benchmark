"""Test configuration loading."""

from pathlib import Path

import pytest

from mrbench.core.config import (
    DEFAULT_CONFIG,
    GeneralConfig,
    load_config,
)


def test_default_config_is_valid():
    config = DEFAULT_CONFIG
    assert config.general.timeout == 300
    assert config.general.store_prompts is False
    assert config.general.enable_network is False


def test_load_config_from_toml(tmp_path: Path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[general]
timeout = 600
store_prompts = true
""")
    config = load_config(config_file)
    assert config.general.timeout == 600
    assert config.general.store_prompts is True


def test_load_config_missing_file_uses_defaults(tmp_path: Path):
    config = load_config(tmp_path / "nonexistent.toml")
    assert config.general.timeout == DEFAULT_CONFIG.general.timeout


def test_config_validates_timeout_positive():
    with pytest.raises(ValueError):
        GeneralConfig(timeout=-1)


def test_routing_preference_order():
    config = DEFAULT_CONFIG
    assert "ollama" in config.routing.preference_order
    assert "claude" in config.routing.preference_order
