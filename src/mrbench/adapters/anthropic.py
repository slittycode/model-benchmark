"""Anthropic API adapter for mrbench.

Wraps the Anthropic API for running LLM inference.
"""

from __future__ import annotations

import os
from typing import Any

from mrbench.adapters.base import (
    Adapter,
    AdapterCapabilities,
    DetectionResult,
    RunOptions,
    RunResult,
)

ANTHROPIC_MODELS = [
    "claude-sonnet-4-20250514",
    "claude-sonnet-4-20250514",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
]


class AnthropicAdapter(Adapter):
    """Adapter for Anthropic API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._base_url = base_url
        self._timeout = timeout
        self._client: Any = None

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def display_name(self) -> str:
        return "Anthropic"

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise ImportError(
                "Anthropic SDK not installed. Install with: pip install mrbench[api]"
            ) from e

        self._client = Anthropic(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
        )
        return self._client

    def detect(self) -> DetectionResult:
        if self._api_key is None:
            return DetectionResult(
                detected=False,
                error="ANTHROPIC_API_KEY not set. Set it in your environment or pass api_key.",
            )

        try:
            client = self._get_client()
            client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            return DetectionResult(
                detected=True,
                auth_status="authenticated",
                trusted=True,
            )
        except Exception as e:
            return DetectionResult(
                detected=True,
                auth_status="error",
                error=f"API connection failed: {e}",
            )

    def list_models(self) -> list[str]:
        return ANTHROPIC_MODELS

    def run(self, prompt: str, options: RunOptions) -> RunResult:
        if self._api_key is None:
            return RunResult(
                output="",
                exit_code=1,
                wall_time_ms=0,
                error="ANTHROPIC_API_KEY not set. Set it in your environment or pass api_key.",
            )

        try:
            import time

            start_time = time.perf_counter()
            client = self._get_client()

            model = options.model or "claude-3-haiku-20240307"

            response = client.messages.create(
                model=model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
                timeout=options.timeout,
            )

            wall_time_ms = (time.perf_counter() - start_time) * 1000

            output = ""
            for block in response.content:
                if hasattr(block, "text"):
                    output += block.text

            return RunResult(
                output=output,
                exit_code=0,
                wall_time_ms=wall_time_ms,
                ttft_ms=None,
                error=None,
            )
        except Exception as e:
            return RunResult(
                output="",
                exit_code=1,
                wall_time_ms=0,
                error=str(e),
            )

    def get_capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            name=self.name,
            streaming=True,
            tool_calling=True,
            supports_system_prompt=True,
            offline=False,
        )
