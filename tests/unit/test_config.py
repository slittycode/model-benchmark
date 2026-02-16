"""Test configuration loading."""

from pathlib import Path

import pytest

from mrbench.core.config import (
    DEFAULT_CONFIG,
    GeneralConfig,
    get_default_config_path,
    get_default_data_path,
    load_config,
    merge_config,
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


def test_load_config_missing_file_returns_independent_copy(tmp_path: Path):
    config_a = load_config(tmp_path / "missing.toml")
    config_a.routing.preference_order.append("mutated-provider")

    config_b = load_config(tmp_path / "missing.toml")
    assert "mutated-provider" not in config_b.routing.preference_order


def test_config_validates_timeout_positive():
    with pytest.raises(ValueError):
        GeneralConfig(timeout=-1)


def test_routing_preference_order():
    config = DEFAULT_CONFIG
    assert "ollama" in config.routing.preference_order
    assert "claude" in config.routing.preference_order


def test_default_path_helpers():
    config_path = get_default_config_path()
    data_path = get_default_data_path()

    assert str(config_path).endswith("/.config/mrbench/config.toml")
    assert str(data_path).endswith("/.local/share/mrbench")


def test_load_config_invalid_toml_warns_and_uses_defaults(tmp_path: Path):
    config_file = tmp_path / "invalid.toml"
    config_file.write_text("[general\ninvalid = true")

    with pytest.warns(UserWarning, match="Failed to load config"):
        config = load_config(config_file)

    assert config.general.timeout == DEFAULT_CONFIG.general.timeout


def test_load_config_invalid_toml_returns_independent_copy(tmp_path: Path):
    config_file = tmp_path / "invalid.toml"
    config_file.write_text("[general\ninvalid = true")

    with pytest.warns(UserWarning):
        config_a = load_config(config_file)
    config_a.routing.preference_order.append("mutated-provider")

    with pytest.warns(UserWarning):
        config_b = load_config(config_file)
    assert "mutated-provider" not in config_b.routing.preference_order


def test_merge_config_deep_merge():
    merged = merge_config(
        DEFAULT_CONFIG,
        {
            "general": {"timeout": 120, "store_prompts": True},
            "providers": {"ollama": {"default_model": "llama3.2", "enabled": True}},
            "logging": {"level": "DEBUG"},
        },
    )

    assert merged.general.timeout == 120
    assert merged.general.store_prompts is True
    assert merged.logging.level == "DEBUG"
    assert merged.providers["ollama"].default_model == "llama3.2"
