"""Adapters package for mrbench."""

from mrbench.adapters.base import Adapter, AdapterCapabilities, DetectionResult, RunResult
from mrbench.adapters.registry import AdapterRegistry, get_default_registry

__all__ = [
    "Adapter",
    "AdapterCapabilities",
    "AdapterRegistry",
    "DetectionResult",
    "RunResult",
    "get_default_registry",
]
