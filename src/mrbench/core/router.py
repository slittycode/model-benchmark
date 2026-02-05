"""Router policy engine for mrbench.

Implements routing policies to select optimal providers based on constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mrbench.adapters.base import Adapter


class RoutingPolicy(Enum):
    """Available routing policies."""

    PREFERENCE = "preference"  # Use preference order
    FASTEST = "fastest"  # Select based on historical latency
    CHEAPEST = "cheapest"  # Select based on cost
    OFFLINE_ONLY = "offline_only"  # Only local models


@dataclass
class RoutingConstraints:
    """Constraints for provider selection."""

    offline_only: bool = False
    streaming_required: bool = False
    max_context: int | None = None
    max_latency_ms: int | None = None
    tool_calling_required: bool = False


@dataclass
class RoutingResult:
    """Result of routing decision."""

    provider: str
    model: str
    reasons: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)


class Router:
    """Selects optimal provider based on policy and constraints."""

    def __init__(
        self,
        policy: RoutingPolicy = RoutingPolicy.PREFERENCE,
        preference_order: list[str] | None = None,
    ) -> None:
        self._policy = policy
        self._preference_order = preference_order or [
            "ollama",
            "claude",
            "codex",
            "gemini",
            "goose",
            "opencode",
        ]

    def route(
        self,
        adapters: list[Adapter],
        constraints: RoutingConstraints | None = None,
        default_models: dict[str, str] | None = None,
    ) -> RoutingResult | None:
        """Select the best provider based on policy and constraints.

        Args:
            adapters: List of available adapters.
            constraints: Optional routing constraints.
            default_models: Map of provider name to default model.

        Returns:
            RoutingResult if a provider was selected, None if no match.
        """
        if not adapters:
            return None

        constraints = constraints or RoutingConstraints()
        default_models = default_models or {}

        # Filter by constraints
        candidates: list[tuple[Adapter, list[str]]] = []

        for adapter in adapters:
            caps = adapter.get_capabilities()
            reasons: list[str] = []

            # Check offline constraint
            if constraints.offline_only and not caps.offline:
                continue

            # Check streaming constraint
            if constraints.streaming_required and not caps.streaming:
                continue

            # Check tool calling constraint
            if constraints.tool_calling_required and not caps.tool_calling:
                continue

            # Check context constraint
            if (
                constraints.max_context
                and caps.max_context
                and caps.max_context < constraints.max_context
            ):
                continue

            reasons.append(f"{adapter.name} is available")
            candidates.append((adapter, reasons))

        if not candidates:
            return None

        # Sort by policy
        if self._policy == RoutingPolicy.PREFERENCE:
            candidates = self._sort_by_preference(candidates)
        elif self._policy == RoutingPolicy.OFFLINE_ONLY:
            # Filter to offline only (already done in constraints)
            candidates = [(a, r) for a, r in candidates if a.get_capabilities().offline]
        # FASTEST and CHEAPEST would need historical data - stub for now

        if not candidates:
            return None

        selected, reasons = candidates[0]
        alternatives = [a.name for a, _ in candidates[1:4]]

        # Get model
        model = default_models.get(selected.name)
        if not model:
            models = selected.list_models()
            model = models[0] if models else "default"

        # Add preference reason
        if selected.name in self._preference_order:
            idx = self._preference_order.index(selected.name)
            reasons.append(f"Ranked #{idx + 1} in preference order")

        return RoutingResult(
            provider=selected.name,
            model=model,
            reasons=reasons,
            alternatives=alternatives,
        )

    def _sort_by_preference(
        self, candidates: list[tuple[Adapter, list[str]]]
    ) -> list[tuple[Adapter, list[str]]]:
        """Sort candidates by preference order."""

        def key(item: tuple[Adapter, list[str]]) -> int:
            adapter, _ = item
            try:
                return self._preference_order.index(adapter.name)
            except ValueError:
                return len(self._preference_order)

        return sorted(candidates, key=key)
