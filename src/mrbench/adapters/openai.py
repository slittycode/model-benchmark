"""OpenAI API adapter for mrbench.

Wraps the OpenAI API for running LLM inference.
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

OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
]


class OpenAIAdapter(Adapter):
    """Adapter for OpenAI API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url
        self._timeout = timeout
        self._client: Any = None

    @property
    def name(self) -> str:
        return "openai"

    @property
    def display_name(self) -> str:
        return "OpenAI"

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "OpenAI SDK not installed. Install with: pip install mrbench[api]"
            ) from e

        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
        )
        return self._client

    def detect(self) -> DetectionResult:
        if self._api_key is None:
            return DetectionResult(
                detected=False,
                error="OPENAI_API_KEY not set. Set it in your environment or pass api_key.",
            )

        try:
            client = self._get_client()
            client.models.list()
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
        try:
            client = self._get_client()
            models = client.models.list()
            return [m.id for m in models.data]
        except ImportError:
            return OPENAI_MODELS
        except Exception:
            return OPENAI_MODELS

    def run(self, prompt: str, options: RunOptions) -> RunResult:
        if self._api_key is None:
            return RunResult(
                output="",
                exit_code=1,
                wall_time_ms=0,
                error="OPENAI_API_KEY not set. Set it in your environment or pass api_key.",
            )

        try:
            import time

            start_time = time.perf_counter()
            client = self._get_client()

            model = options.model or "gpt-4o-mini"

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=options.timeout,
            )

            wall_time_ms = (time.perf_counter() - start_time) * 1000

            output = response.choices[0].message.content or ""

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
