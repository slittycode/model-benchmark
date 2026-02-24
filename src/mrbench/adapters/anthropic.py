"""Anthropic API adapter for mrbench.

Wraps the Anthropic API for running LLM inference.
"""

from __future__ import annotations

import os
import time
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
        """Detect if Anthropic API is configured.

        Checks for API key presence and format without making a paid API call.
        """
        if self._api_key is None:
            return DetectionResult(
                detected=False,
                error="ANTHROPIC_API_KEY not set. Set it in your environment or pass api_key.",
            )

        # Validate key format (Anthropic keys start with sk-ant-)
        if not self._api_key.startswith("sk-ant-"):
            return DetectionResult(
                detected=True,
                auth_status="error",
                error="Invalid ANTHROPIC_API_KEY format. Expected key starting with 'sk-ant-'.",
            )

        # Check if SDK is available
        try:
            self._get_client()
        except ImportError as e:
            return DetectionResult(
                detected=False,
                error=f"Anthropic SDK not installed: {e}. Install with: pip install mrbench[api]",
            )

        # SDK is available and key format is valid - assume configured
        return DetectionResult(
            detected=True,
            auth_status="authenticated",
            trusted=True,
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

            usage = getattr(response, "usage", None)
            token_count_input = (
                int(usage.input_tokens)
                if usage is not None and getattr(usage, "input_tokens", None) is not None
                else None
            )
            token_count_output = (
                int(usage.output_tokens)
                if usage is not None and getattr(usage, "output_tokens", None) is not None
                else None
            )

            return RunResult(
                output=output,
                exit_code=0,
                wall_time_ms=wall_time_ms,
                ttft_ms=None,
                error=None,
                token_count_input=token_count_input,
                token_count_output=token_count_output,
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
