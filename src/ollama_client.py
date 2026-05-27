"""Small Ollama REST client for local grounded answer generation.

The project intentionally talks to Ollama through its local HTTP API instead of
adding a Python SDK dependency.  This keeps the demo install light and makes the
LLM path optional: if Ollama is not running, the answer layer can fall back to
its deterministic extractive response.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests
from requests import RequestException

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_OLLAMA_TIMEOUT = 30.0
DEFAULT_OLLAMA_TEMPERATURE = 0.1
DEFAULT_OLLAMA_NUM_PREDICT = 512


class OllamaError(RuntimeError):
    """Raised when a local Ollama generation request cannot be completed."""


@dataclass(frozen=True)
class OllamaSettings:
    """Runtime settings for the optional Ollama integration."""

    enabled: bool
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    model: str = DEFAULT_OLLAMA_MODEL
    timeout: float = DEFAULT_OLLAMA_TIMEOUT
    temperature: float = DEFAULT_OLLAMA_TEMPERATURE
    num_predict: int = DEFAULT_OLLAMA_NUM_PREDICT

    @property
    def generate_url(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/api"):
            return f"{base}/generate"
        return f"{base}/api/generate"


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


def load_ollama_settings(*, use_llm: bool | None = None, provider: str | None = None) -> OllamaSettings:
    """Load Ollama settings from explicit flags and environment variables.

    Explicit ``use_llm`` from the Streamlit UI/test call wins over environment
    defaults.  Environment activation is intentionally opt-in so a developer who
    happens to have Ollama installed does not accidentally change deterministic
    demo behavior.
    """
    provider_name = (provider or os.getenv("KD_NOTICE_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "").strip().lower()
    if use_llm is None:
        enabled = provider_name == "ollama" or _env_bool("KD_NOTICE_USE_OLLAMA") or _env_bool("USE_OLLAMA")
    else:
        enabled = bool(use_llm)

    base_url = (
        os.getenv("KD_NOTICE_OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or DEFAULT_OLLAMA_BASE_URL
    ).strip()
    model = (
        os.getenv("KD_NOTICE_OLLAMA_MODEL")
        or os.getenv("OLLAMA_MODEL")
        or DEFAULT_OLLAMA_MODEL
    ).strip()

    timeout = _env_float("KD_NOTICE_OLLAMA_TIMEOUT", DEFAULT_OLLAMA_TIMEOUT)
    temperature = _env_float("KD_NOTICE_OLLAMA_TEMPERATURE", DEFAULT_OLLAMA_TEMPERATURE)
    num_predict = _env_int("KD_NOTICE_OLLAMA_NUM_PREDICT", DEFAULT_OLLAMA_NUM_PREDICT)

    return OllamaSettings(
        enabled=enabled,
        base_url=base_url or DEFAULT_OLLAMA_BASE_URL,
        model=model or DEFAULT_OLLAMA_MODEL,
        timeout=max(timeout, 1.0),
        temperature=max(0.0, temperature),
        num_predict=max(64, num_predict),
    )


def with_ollama_overrides(
    settings: OllamaSettings,
    *,
    base_url: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
    num_predict: int | None = None,
    temperature: float | None = None,
) -> OllamaSettings:
    """Return settings with explicit UI/runtime overrides applied."""
    return OllamaSettings(
        enabled=settings.enabled,
        base_url=(base_url or settings.base_url).strip() or DEFAULT_OLLAMA_BASE_URL,
        model=(model or settings.model).strip() or DEFAULT_OLLAMA_MODEL,
        timeout=max(float(timeout if timeout is not None else settings.timeout), 1.0),
        temperature=max(float(temperature if temperature is not None else settings.temperature), 0.0),
        num_predict=max(int(num_predict if num_predict is not None else settings.num_predict), 64),
    )


def list_ollama_models(base_url: str = DEFAULT_OLLAMA_BASE_URL, *, timeout: float = 2.0) -> list[str]:
    """Return model names from a running Ollama server, or an empty list."""
    tags_url = f"{base_url.rstrip('/')}/api/tags"
    try:
        response = requests.get(tags_url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (RequestException, ValueError):
        return []
    models = data.get("models") if isinstance(data, dict) else []
    names = []
    for item in models if isinstance(models, list) else []:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                names.append(name)
    return sorted(set(names))


def generate_with_ollama(prompt: str, *, settings: OllamaSettings, system: str | None = None) -> dict[str, Any]:
    """Generate a single non-streaming response from Ollama.

    Returns a compact metadata payload instead of the full raw response so UI and
    tests can verify which local model path was used without exposing excessive
    runtime details.
    """
    if not settings.enabled:
        raise OllamaError("Ollama generation was not enabled")
    if not prompt.strip():
        raise OllamaError("Ollama prompt is empty")

    payload: dict[str, Any] = {
        "model": settings.model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": settings.temperature,
            "num_predict": settings.num_predict,
        },
    }
    if system:
        payload["system"] = system

    try:
        response = requests.post(settings.generate_url, json=payload, timeout=settings.timeout)
        response.raise_for_status()
        data = response.json()
    except RequestException as exc:
        raise OllamaError(f"Ollama request failed: {exc}") from exc
    except ValueError as exc:
        raise OllamaError("Ollama returned invalid JSON") from exc

    text = str(data.get("response") or "").strip()
    if not text:
        raise OllamaError("Ollama returned an empty response")

    return {
        "text": text,
        "model": str(data.get("model") or settings.model),
        "done": bool(data.get("done", True)),
        "eval_count": data.get("eval_count"),
    }
