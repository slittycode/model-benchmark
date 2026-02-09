"""Configuration detection for AI CLI tools.

Provides utilities to detect and validate AI CLI configurations
in standard locations like ~/.config, ~/.local/share, etc.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mrbench.core.executor import SubprocessExecutor


@dataclass
class ConfigCheckResult:
    """Result of checking an AI CLI configuration."""

    provider: str
    has_binary: bool = False
    has_config: bool = False
    has_auth: bool = False
    config_path: str | None = None
    auth_status: str = "unknown"
    check_output: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """Check if the CLI is fully configured and ready to use."""
        return self.has_binary and (self.has_config or self.has_auth)


# Standard config locations for various AI CLIs
CONFIG_LOCATIONS: dict[str, list[str]] = {
    "claude": [
        "~/.claude",
        "~/.config/claude",
        "~/.claude.json",
    ],
    "codex": [
        "~/.codex",
        "~/.config/codex",
    ],
    "gemini": [
        "~/.config/gemini",
        "~/.gemini",
    ],
    "ollama": [
        "~/.ollama",
    ],
    "goose": [
        "~/.config/goose",
        "~/.goose",
    ],
    "opencode": [
        "~/.opencode",
        "~/.config/opencode",
    ],
    "aider": [
        "~/.aider",
        "~/.config/aider",
        "~/.aider.conf.yml",
    ],
    "cursor": [
        "~/.cursor",
        "~/Library/Application Support/Cursor",
    ],
    "continue": [
        "~/.continue",
    ],
    "aws": [
        "~/.aws/credentials",
        "~/.aws/config",
    ],
    "gcloud": [
        "~/.config/gcloud",
    ],
    "azure": [
        "~/.azure",
    ],
}

# Auth check commands for various CLIs
AUTH_CHECK_COMMANDS: dict[str, list[str]] = {
    "claude": ["claude", "--version"],  # Just verify it runs
    "codex": ["codex", "--version"],
    "gemini": ["gemini", "--version"],
    "ollama": ["ollama", "list"],  # List models to verify server is running
    "goose": ["goose", "--version"],
    "opencode": ["opencode", "--version"],
    "aws": ["aws", "sts", "get-caller-identity"],  # Verify AWS auth
    "gcloud": ["gcloud", "auth", "list"],  # List authenticated accounts
    "azure": ["az", "account", "show"],  # Show current account
    "gh": ["gh", "auth", "status"],  # GitHub CLI auth status
}


class ConfigDetector:
    """Detects AI CLI configurations across the system."""

    def __init__(self, timeout: float = 10.0) -> None:
        self._executor = SubprocessExecutor(timeout=timeout)
        self._home = Path.home()

    def check_provider(self, provider: str) -> ConfigCheckResult:
        """Check configuration for a specific provider.

        Args:
            provider: Name of the provider to check.

        Returns:
            ConfigCheckResult with detection details.
        """
        result = ConfigCheckResult(provider=provider)

        # Check binary
        binary = shutil.which(provider)
        result.has_binary = binary is not None

        # Check config locations
        config_paths = CONFIG_LOCATIONS.get(provider, [])
        for config_path in config_paths:
            expanded = Path(os.path.expanduser(config_path))
            if expanded.exists():
                result.has_config = True
                result.config_path = str(expanded)
                break

        # Run auth check command if available
        auth_cmd = AUTH_CHECK_COMMANDS.get(provider)
        if auth_cmd and result.has_binary:
            try:
                exec_result = self._executor.run(auth_cmd)
                result.has_auth = exec_result.exit_code == 0
                result.auth_status = "authenticated" if result.has_auth else "not_authenticated"
                result.check_output = exec_result.stdout[:500] if exec_result.stdout else None
            except Exception as e:
                result.errors.append(f"Auth check failed: {e}")
                result.auth_status = "error"

        return result

    def check_all(self) -> list[ConfigCheckResult]:
        """Check all known providers.

        Returns:
            List of ConfigCheckResult for each provider.
        """
        results = []
        for provider in CONFIG_LOCATIONS:
            results.append(self.check_provider(provider))
        return results

    def check_available(self) -> list[ConfigCheckResult]:
        """Check only providers that have binaries installed.

        Returns:
            List of ConfigCheckResult for providers with binaries.
        """
        results = []
        for provider in CONFIG_LOCATIONS:
            result = self.check_provider(provider)
            if result.has_binary:
                results.append(result)
        return results

    def discover_cli_tools(self, check_auth: bool = False) -> dict[str, Any]:
        """Discover all AI/coding CLI tools on the system.

        Searches for common AI CLI tools and checks their status.

        Args:
            check_auth: When True, run auth check commands for installed tools.

        Returns:
            Dictionary with discovery results.
        """
        # Known AI CLI binaries to look for
        cli_tools = [
            # AI Agents & Assistants
            "claude",
            "codex",
            "gemini",
            "ollama",
            "goose",
            "opencode",
            "aider",
            "cursor",
            "continue",
            "cody",
            "copilot",
            # Cloud CLIs with AI capabilities
            "aws",
            "gcloud",
            "az",
            "gh",
            # Local inference
            "llama-cli",
            "vllm",
            "mlx_lm",
            # Other coding tools
            "kilocode",
            "sourcegraph",
            "tabnine",
        ]

        discovered: dict[str, Any] = {
            "installed": [],
            "configured": [],
            "ready": [],
            "not_found": [],
        }

        for tool in cli_tools:
            binary = shutil.which(tool)
            if binary:
                info = {
                    "name": tool,
                    "path": binary,
                    "has_config": False,
                    "config_path": None,
                }

                # Check for config
                config_paths = CONFIG_LOCATIONS.get(tool, [])
                for config_path in config_paths:
                    expanded = Path(os.path.expanduser(config_path))
                    if expanded.exists():
                        info["has_config"] = True
                        info["config_path"] = str(expanded)
                        break

                discovered["installed"].append(info)
                if info["has_config"]:
                    discovered["configured"].append(info)

                if check_auth:
                    # Run auth checks only when explicitly requested.
                    auth_cmd = AUTH_CHECK_COMMANDS.get(tool)
                    if auth_cmd:
                        try:
                            result = self._executor.run(auth_cmd)
                            info["auth_status"] = (
                                "authenticated" if result.exit_code == 0 else "not_authenticated"
                            )
                            if result.exit_code == 0:
                                discovered["ready"].append(info)
                        except Exception as e:
                            info["auth_status"] = "error"
                            info["auth_error"] = str(e)
            else:
                discovered["not_found"].append(tool)

        return discovered
