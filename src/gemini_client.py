"""Small Gemini API REST client for optional grounded answer generation.

The app keeps Gemini support dependency-light by using the public REST
``models.generateContent`` endpoint directly through ``requests``.  If an API
key is missing or the request fails, callers can fall back to the deterministic
extractive answer path.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests
from requests import RequestException

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_TIMEOUT = 30.0
DEFAULT_GEMINI_TEMPERATURE = 0.1
DEFAULT_GEMINI_MAX_OUTPUT_TOKENS = 512


class GeminiError(RuntimeError):
    """Raised when Gemini generation cannot be completed."""


@dataclass(frozen=True)
class GeminiSettings:
    """Runtime settings for optional Gemini API generation."""

    enabled: bool
    api_key: str = ""
    base_url: str = DEFAULT_GEMINI_BASE_URL
    model: str = DEFAULT_GEMINI_MODEL
    timeout: float = DEFAULT_GEMINI_TIMEOUT
    temperature: float = DEFAULT_GEMINI_TEMPERATURE
    max_output_tokens: int = DEFAULT_GEMINI_MAX_OUTPUT_TOKENS

    @property
    def generate_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/models/{self.model}:generateContent"


def _env_bool(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def load_gemini_settings(*, use_llm: bool | None = None, provider: str | None = None) -> GeminiSettings:
    """Load Gemini settings from explicit flags and environment variables."""
    provider_name = (provider or os.getenv("KD_NOTICE_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "").strip().lower()
    if use_llm is None:
        enabled = provider_name == "gemini" or _env_bool("KD_NOTICE_USE_GEMINI") or _env_bool("USE_GEMINI")
    else:
        enabled = bool(use_llm) and provider_name == "gemini"

    api_key = (
        os.getenv("KD_NOTICE_GEMINI_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    ).strip()
    base_url = (os.getenv("KD_NOTICE_GEMINI_BASE_URL") or DEFAULT_GEMINI_BASE_URL).strip()
    model = (os.getenv("KD_NOTICE_GEMINI_MODEL") or os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip()
    timeout = _env_float("KD_NOTICE_GEMINI_TIMEOUT", DEFAULT_GEMINI_TIMEOUT)
    temperature = _env_float("KD_NOTICE_GEMINI_TEMPERATURE", DEFAULT_GEMINI_TEMPERATURE)
    max_output_tokens = _env_int("KD_NOTICE_GEMINI_MAX_OUTPUT_TOKENS", DEFAULT_GEMINI_MAX_OUTPUT_TOKENS)

    return GeminiSettings(
        enabled=enabled,
        api_key=api_key,
        base_url=base_url or DEFAULT_GEMINI_BASE_URL,
        model=model or DEFAULT_GEMINI_MODEL,
        timeout=max(timeout, 1.0),
        temperature=max(0.0, temperature),
        max_output_tokens=max(64, max_output_tokens),
    )


def with_gemini_overrides(
    settings: GeminiSettings,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
) -> GeminiSettings:
    """Return settings with explicit UI/runtime overrides applied."""
    api_key_override = (api_key or "").strip()
    return GeminiSettings(
        enabled=settings.enabled,
        api_key=api_key_override or settings.api_key,
        base_url=(base_url or settings.base_url).strip() or DEFAULT_GEMINI_BASE_URL,
        model=(model or settings.model).strip() or DEFAULT_GEMINI_MODEL,
        timeout=max(float(timeout if timeout is not None else settings.timeout), 1.0),
        temperature=max(float(temperature if temperature is not None else settings.temperature), 0.0),
        max_output_tokens=max(int(max_output_tokens if max_output_tokens is not None else settings.max_output_tokens), 64),
    )


def generate_with_gemini(prompt: str, *, settings: GeminiSettings, system: str | None = None) -> dict[str, Any]:
    """Generate a single non-streaming response from Gemini REST API."""
    if not settings.enabled:
        raise GeminiError("Gemini generation was not enabled")
    if not settings.api_key:
        raise GeminiError("Gemini API key is missing")
    if not prompt.strip():
        raise GeminiError("Gemini prompt is empty")

    payload: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": settings.temperature,
            "maxOutputTokens": settings.max_output_tokens,
        },
    }
    if system:
        payload["system_instruction"] = {"parts": [{"text": system}]}

    try:
        response = requests.post(
            settings.generate_url,
            headers={"x-goog-api-key": settings.api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=settings.timeout,
        )
        response.raise_for_status()
        data = response.json()
    except RequestException as exc:
        raise GeminiError(f"Gemini request failed: {exc}") from exc
    except ValueError as exc:
        raise GeminiError("Gemini returned invalid JSON") from exc

    text_parts: list[str] = []
    candidates = data.get("candidates") if isinstance(data, dict) else []
    for candidate in candidates if isinstance(candidates, list) else []:
        content = candidate.get("content") if isinstance(candidate, dict) else {}
        parts = content.get("parts") if isinstance(content, dict) else []
        for part in parts if isinstance(parts, list) else []:
            if isinstance(part, dict) and str(part.get("text") or "").strip():
                text_parts.append(str(part["text"]).strip())
    text = "\n".join(text_parts).strip()
    if not text:
        raise GeminiError("Gemini returned an empty response")

    return {
        "text": text,
        "model": settings.model,
        "candidate_count": len(candidates) if isinstance(candidates, list) else None,
    }
