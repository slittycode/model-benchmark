"""Configuration loading and validation for mrbench."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


def get_default_config_path() -> Path:
    """Get the default config file path."""
    return Path.home() / ".config" / "mrbench" / "config.toml"


def get_default_data_path() -> Path:
    """Get the default data directory path."""
    return Path.home() / ".local" / "share" / "mrbench"


class GeneralConfig(BaseModel):
    """General configuration settings."""

    output_dir: str = "./out"
    timeout: int = Field(default=300, ge=1, le=3600)
    store_prompts: bool = False
    enable_network: bool = False

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 1:
            raise ValueError("timeout must be positive")
        return v


class DiscoveryConfig(BaseModel):
    """Discovery configuration settings."""

    extra_paths: list[str] = Field(default_factory=lambda: ["~/bin", "~/.local/bin"])
    trusted_paths: list[str] = Field(
        default_factory=lambda: [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "~/.local/bin",
        ]
    )


class RoutingConstraints(BaseModel):
    """Routing constraint defaults."""

    offline_only: bool = False
    max_latency_ms: int = 30000
    streaming_required: bool = False


class RoutingConfig(BaseModel):
    """Routing configuration settings."""

    default_policy: str = "preference"
    preference_order: list[str] = Field(
        default_factory=lambda: ["ollama", "claude", "codex", "gemini", "goose", "opencode"]
    )
    constraints: RoutingConstraints = Field(default_factory=RoutingConstraints)


class ProviderConfig(BaseModel):
    """Per-provider configuration."""

    enabled: bool = True
    binary: str | None = None
    default_model: str | None = None


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    redact_secrets: bool = True


class MrbenchConfig(BaseModel):
    """Root configuration model."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


# Default configuration instance
DEFAULT_CONFIG = MrbenchConfig()


def load_config(config_path: Path | None = None) -> MrbenchConfig:
    """Load configuration from TOML file.

    Args:
        config_path: Path to config file. If None, uses default location.

    Returns:
        Loaded and validated configuration.
    """
    if config_path is None:
        config_path = get_default_config_path()

    if not config_path.exists():
        return DEFAULT_CONFIG

    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        return MrbenchConfig.model_validate(data)
    except (OSError, tomllib.TOMLDecodeError) as e:
        # Log warning but return defaults
        import warnings

        warnings.warn(f"Failed to load config from {config_path}: {e}")
        return DEFAULT_CONFIG


def merge_config(base: MrbenchConfig, overrides: dict[str, Any]) -> MrbenchConfig:
    """Merge config overrides into base config.

    Args:
        base: Base configuration.
        overrides: Dictionary of overrides to apply.

    Returns:
        New merged configuration.
    """
    base_dict = base.model_dump()

    def deep_merge(d1: dict[str, Any], d2: dict[str, Any]) -> dict[str, Any]:
        result = d1.copy()
        for key, value in d2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    merged = deep_merge(base_dict, overrides)
    return MrbenchConfig.model_validate(merged)
