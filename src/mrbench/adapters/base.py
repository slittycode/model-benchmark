"""Base adapter class for mrbench.

All provider adapters must inherit from `Adapter` and implement its abstract methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdapterCapabilities:
    """Describes capabilities of an adapter."""

    name: str
    streaming: bool = False
    tool_calling: bool = False
    max_tokens: int | None = None
    max_context: int | None = None
    supports_system_prompt: bool = True
    offline: bool = False  # True for local-only models
    cost_per_1k_input: float | None = None
    cost_per_1k_output: float | None = None


@dataclass
class DetectionResult:
    """Result of adapter detection."""

    detected: bool
    binary_path: str | None = None
    version: str | None = None
    auth_status: str | None = None  # "authenticated", "unauthenticated", "unknown"
    trusted: bool = True  # False if binary found in untrusted location
    error: str | None = None


@dataclass
class RunResult:
    """Result of running a prompt through an adapter."""

    output: str
    exit_code: int
    wall_time_ms: float
    ttft_ms: float | None = None
    error: str | None = None
    token_count_input: int | None = None
    token_count_output: int | None = None
    tokens_estimated: bool = False
    raw_response: dict[str, Any] | None = None
    chunks: list[str] = field(default_factory=list)


@dataclass
class RunOptions:
    """Options for running a prompt."""

    model: str
    stream: bool = False
    timeout: float = 300.0
    max_tokens: int | None = None
    temperature: float | None = None
    system_prompt: str | None = None
    stream_callback: Callable[[str], None] | None = None


class Adapter(ABC):
    """Abstract base class for provider adapters.

    Each adapter wraps an external CLI tool and provides a consistent interface
    for detection, model listing, and prompt execution.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this adapter (e.g., 'ollama', 'claude')."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name for display."""
        return self.name.title()

    @abstractmethod
    def detect(self) -> DetectionResult:
        """Detect if the provider CLI is installed and accessible.

        Returns:
            DetectionResult with detection status and metadata.
        """
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """List available models for this provider.

        Returns:
            List of model identifiers. Empty if listing not supported.
        """
        ...

    @abstractmethod
    def run(self, prompt: str, options: RunOptions) -> RunResult:
        """Run a prompt through the provider.

        Args:
            prompt: The prompt text to send.
            options: Run configuration options.

        Returns:
            RunResult with output and metrics.
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> AdapterCapabilities:
        """Get capability information for this adapter.

        Returns:
            AdapterCapabilities describing what this adapter supports.
        """
        ...

    def check_auth(self) -> str:
        """Check authentication status.

        Returns:
            One of: "authenticated", "unauthenticated", "unknown"
        """
        result = self.detect()
        return result.auth_status or "unknown"

    def is_available(self) -> bool:
        """Check if this adapter is available for use.

        Returns:
            True if the provider is detected and appears usable.
        """
        result = self.detect()
        return result.detected
