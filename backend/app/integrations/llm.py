"""LLM provider abstraction supporting local Ollama and future cloud fallbacks."""

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import settings


class BaseLLMProvider(ABC):
    """Abstract interface for LLM inference providers."""

    provider_name: str

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        """Return truthful connectivity and model readiness status."""


class OllamaProvider(BaseLLMProvider):
    """Local Ollama HTTP API integration (default local-first provider)."""

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout_seconds = timeout_seconds or settings.OLLAMA_TIMEOUT_SECONDS

    def check_health(self) -> dict[str, Any]:
        """Query Ollama GET /api/tags and verify reachability and installed models."""
        start = time.perf_counter()
        url = f"{self.base_url}/api/tags"
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()

            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            models_raw = payload.get("models", []) if isinstance(payload, dict) else []
            installed_models = [
                m.get("name") for m in models_raw if isinstance(m, dict) and m.get("name")
            ]
            model_available = any(
                name == self.model or name.startswith(f"{self.model}:")
                for name in installed_models
            )

            return {
                "status": "healthy",
                "service": "ollama",
                "latency_ms": latency_ms,
                "details": {
                    "base_url": self.base_url,
                    "configured_model": self.model,
                    "configured_model_available": model_available,
                    "installed_models": installed_models,
                },
                "error": None,
            }
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "unhealthy",
                "service": "ollama",
                "latency_ms": latency_ms,
                "details": {
                    "base_url": self.base_url,
                    "configured_model": self.model,
                },
                "error": f"{type(exc).__name__}: {str(exc)}",
            }


class CloudFallbackProviderStub(BaseLLMProvider):
    """
    Integration-ready provider stub for future OpenRouter, Gemini, and Groq usage.
    No paid API keys are required in M0.
    """

    def __init__(self, provider_name: str, model: str, api_key_configured: bool) -> None:
        self.provider_name = provider_name
        self.model = model
        self.api_key_configured = api_key_configured

    def check_health(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self.api_key_configured else "unconfigured",
            "service": self.provider_name,
            "latency_ms": None,
            "details": {
                "model": self.model,
                "api_key_configured": self.api_key_configured,
            },
            "error": None if self.api_key_configured else "Optional cloud API key not set.",
        }

