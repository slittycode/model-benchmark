"""Test configuration for mrbench."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """Create a temporary config file."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[general]
timeout = 600
store_prompts = true

[routing]
default_policy = "preference"
preference_order = ["fake", "ollama"]
""")
    return config_file


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test.db"
