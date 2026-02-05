"""Adapter registry for mrbench.

Manages adapter discovery, registration, and lookup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mrbench.adapters.base import Adapter, DetectionResult


class AdapterRegistry:
    """Registry for managing provider adapters."""

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._adapters: dict[str, Adapter] = {}

    def register(self, adapter: Adapter) -> None:
        """Register an adapter.

        Args:
            adapter: Adapter instance to register.
        """
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> Adapter | None:
        """Get adapter by name.

        Args:
            name: Adapter name (e.g., "ollama").

        Returns:
            Adapter instance or None if not found.
        """
        return self._adapters.get(name)

    def list_all(self) -> list[Adapter]:
        """List all registered adapters.

        Returns:
            List of all adapter instances.
        """
        return list(self._adapters.values())

    def list_names(self) -> list[str]:
        """List all registered adapter names.

        Returns:
            List of adapter names.
        """
        return list(self._adapters.keys())

    def detect_all(self) -> list[DetectionResult]:
        """Run detection on all registered adapters.

        Returns:
            List of detection results for adapters that were detected.
        """

        results: list[DetectionResult] = []
        for adapter in self._adapters.values():
            result = adapter.detect()
            if result.detected:
                results.append(result)
        return results

    def get_available(self) -> list[Adapter]:
        """Get all available (detected) adapters.

        Returns:
            List of adapters that are currently available.
        """
        return [adapter for adapter in self._adapters.values() if adapter.is_available()]


# Default registry instance - lazily initialized
_default_registry: AdapterRegistry | None = None


def get_default_registry() -> AdapterRegistry:
    """Get the default adapter registry with all built-in adapters registered.

    Returns:
        Configured AdapterRegistry instance.
    """
    global _default_registry

    if _default_registry is None:
        _default_registry = AdapterRegistry()

        # Register built-in adapters
        from mrbench.adapters.fake import FakeAdapter
        from mrbench.adapters.ollama import OllamaAdapter

        _default_registry.register(FakeAdapter())
        _default_registry.register(OllamaAdapter())

        # Register other adapters (they'll return not detected if not installed)
        from mrbench.adapters.claude import ClaudeAdapter
        from mrbench.adapters.codex import CodexAdapter
        from mrbench.adapters.gemini import GeminiAdapter
        from mrbench.adapters.goose import GooseAdapter
        from mrbench.adapters.opencode import OpenCodeAdapter

        _default_registry.register(ClaudeAdapter())
        _default_registry.register(CodexAdapter())
        _default_registry.register(GeminiAdapter())
        _default_registry.register(GooseAdapter())
        _default_registry.register(OpenCodeAdapter())

        # Local inference adapters
        from mrbench.adapters.llamacpp import LlamaCppAdapter
        from mrbench.adapters.vllm import VllmAdapter

        _default_registry.register(LlamaCppAdapter())
        _default_registry.register(VllmAdapter())

    return _default_registry


def reset_default_registry() -> None:
    """Reset the default registry (useful for testing)."""
    global _default_registry
    _default_registry = None
