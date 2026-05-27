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
DEFAULT_GEMINI_THINKING_BUDGET = -1


@dataclass(frozen=True)
class GeminiModelProfile:
    """Known Gemini model limits used by the Streamlit settings UI."""

    code: str
    label: str
    output_token_limit: int
    default_output_tokens: int
    thinking_budget_min: int
    thinking_budget_max: int
    default_thinking_budget: int
    can_disable_thinking: bool
    thinking_control: str = "budget"
    thinking_level_options: tuple[str, ...] = ()
    default_thinking_level: str = ""
    notes: str = ""


GEMINI_MODEL_PROFILES: tuple[GeminiModelProfile, ...] = (
    GeminiModelProfile(
        code="gemini-3.5-flash",
        label="Gemini 3.5 Flash — 최신 안정/무료 우선",
        output_token_limit=65536,
        default_output_tokens=768,
        thinking_budget_min=0,
        thinking_budget_max=0,
        default_thinking_budget=0,
        can_disable_thinking=False,
        thinking_control="level",
        thinking_level_options=("minimal", "low", "medium", "high"),
        default_thinking_level="medium",
        notes="Gemini 3 계열은 thinkingBudget 대신 thinkingLevel을 사용",
    ),
    GeminiModelProfile(
        code="gemini-3-flash-preview",
        label="Gemini 3 Flash Preview — 최신 Flash 미리보기",
        output_token_limit=65536,
        default_output_tokens=768,
        thinking_budget_min=0,
        thinking_budget_max=0,
        default_thinking_budget=0,
        can_disable_thinking=False,
        thinking_control="level",
        thinking_level_options=("minimal", "low", "medium", "high"),
        default_thinking_level="medium",
        notes="Preview 모델은 변경/제한 가능성이 있어 무료 플랜에서 계정별로 다를 수 있음",
    ),
    GeminiModelProfile(
        code="gemini-3.1-flash-lite",
        label="Gemini 3.1 Flash-Lite — 최신 경량/고속",
        output_token_limit=65536,
        default_output_tokens=512,
        thinking_budget_min=0,
        thinking_budget_max=0,
        default_thinking_budget=0,
        can_disable_thinking=False,
        thinking_control="level",
        thinking_level_options=("minimal", "low", "medium", "high"),
        default_thinking_level="minimal",
        notes="경량 모델: RAG 요약에는 minimal/low 권장",
    ),
    GeminiModelProfile(
        code="gemini-3.1-flash-lite-preview",
        label="Gemini 3.1 Flash-Lite Preview — 경량 미리보기",
        output_token_limit=65536,
        default_output_tokens=512,
        thinking_budget_min=0,
        thinking_budget_max=0,
        default_thinking_budget=0,
        can_disable_thinking=False,
        thinking_control="level",
        thinking_level_options=("minimal", "low", "medium", "high"),
        default_thinking_level="minimal",
        notes="Preview 모델은 변경/제한 가능성이 있어 무료 플랜에서 계정별로 다를 수 있음",
    ),
    GeminiModelProfile(
        code="gemini-3.1-pro-preview",
        label="Gemini 3.1 Pro Preview — 고급 추론 미리보기",
        output_token_limit=65536,
        default_output_tokens=1024,
        thinking_budget_min=0,
        thinking_budget_max=0,
        default_thinking_budget=0,
        can_disable_thinking=False,
        thinking_control="level",
        thinking_level_options=("low", "medium", "high"),
        default_thinking_level="high",
        notes="Pro 계열은 thinking 비활성화 불가. 무료 플랜 접근은 계정/지역별로 다를 수 있음",
    ),
    GeminiModelProfile(
        code="gemini-2.5-flash",
        label="Gemini 2.5 Flash — 균형/저지연",
        output_token_limit=65536,
        default_output_tokens=768,
        thinking_budget_min=0,
        thinking_budget_max=24576,
        default_thinking_budget=-1,
        can_disable_thinking=True,
        notes="동적 thinking 기본값, 필요 시 thinkingBudget=0으로 비용/지연 최소화 가능",
    ),
    GeminiModelProfile(
        code="gemini-2.5-flash-lite",
        label="Gemini 2.5 Flash-Lite — 최저비용/고속",
        output_token_limit=65536,
        default_output_tokens=512,
        thinking_budget_min=512,
        thinking_budget_max=24576,
        default_thinking_budget=0,
        can_disable_thinking=True,
        notes="기본적으로 thinking을 거의 쓰지 않는 경량 모델",
    ),
    GeminiModelProfile(
        code="gemini-2.5-pro",
        label="Gemini 2.5 Pro — 고품질/추론",
        output_token_limit=65536,
        default_output_tokens=1024,
        thinking_budget_min=128,
        thinking_budget_max=32768,
        default_thinking_budget=-1,
        can_disable_thinking=False,
        notes="고품질 추론 모델, thinking 비활성화 불가",
    ),
    GeminiModelProfile(
        code="gemini-2.0-flash",
        label="Gemini 2.0 Flash — 레거시 안정/고속",
        output_token_limit=8192,
        default_output_tokens=512,
        thinking_budget_min=0,
        thinking_budget_max=0,
        default_thinking_budget=0,
        can_disable_thinking=False,
        thinking_control="none",
        notes="thinking 설정 없이 빠르게 동작하는 2.0 계열",
    ),
    GeminiModelProfile(
        code="gemini-2.0-flash-lite",
        label="Gemini 2.0 Flash-Lite — 레거시 최저비용",
        output_token_limit=8192,
        default_output_tokens=512,
        thinking_budget_min=0,
        thinking_budget_max=0,
        default_thinking_budget=0,
        can_disable_thinking=False,
        thinking_control="none",
        notes="thinking 설정 없이 빠르게 동작하는 2.0 경량 모델",
    ),
)


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
    thinking_budget: int | None = DEFAULT_GEMINI_THINKING_BUDGET
    thinking_level: str | None = None

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


def get_gemini_model_profiles() -> tuple[GeminiModelProfile, ...]:
    """Return selectable Gemini model profiles for this text-only RAG app."""
    return GEMINI_MODEL_PROFILES


def gemini_profile_for_model(model: str) -> GeminiModelProfile:
    """Return a known profile, falling back to Flash defaults for unknown models."""
    normalized = (model or "").strip()
    for profile in GEMINI_MODEL_PROFILES:
        if profile.code == normalized:
            return profile
    for profile in GEMINI_MODEL_PROFILES:
        if profile.code == DEFAULT_GEMINI_MODEL:
            return profile
    return GEMINI_MODEL_PROFILES[0]


def _normalize_thinking_budget(value: int | None, profile: GeminiModelProfile) -> int | None:
    if profile.thinking_control != "budget":
        return None
    if value is None:
        return None
    budget = int(value)
    if budget == -1:
        return -1
    if budget == 0 and profile.can_disable_thinking:
        return 0
    return max(profile.thinking_budget_min, min(profile.thinking_budget_max, budget))


def _normalize_thinking_level(value: str | None, profile: GeminiModelProfile) -> str | None:
    if profile.thinking_control != "level":
        return None
    level = (value or profile.default_thinking_level or "").strip().lower()
    if level in profile.thinking_level_options:
        return level
    return profile.default_thinking_level or None


def list_gemini_models(api_key: str, base_url: str = DEFAULT_GEMINI_BASE_URL, *, timeout: float = 3.0) -> list[str]:
    """Return model codes available to the provided Gemini API key, or [] on failure."""
    if not api_key.strip():
        return []
    try:
        response = requests.get(
            f"{base_url.rstrip('/')}/models",
            headers={"x-goog-api-key": api_key.strip()},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except (RequestException, ValueError):
        return []
    models = data.get("models") if isinstance(data, dict) else []
    output: list[str] = []
    for item in models if isinstance(models, list) else []:
        if not isinstance(item, dict):
            continue
        methods = item.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        name = str(item.get("name") or "").strip()
        if name.startswith("models/"):
            output.append(name.removeprefix("models/"))
    return sorted(set(output))


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
    profile = gemini_profile_for_model(model)
    default_thinking_budget = _env_int("KD_NOTICE_GEMINI_THINKING_BUDGET", profile.default_thinking_budget)
    default_thinking_level = os.getenv("KD_NOTICE_GEMINI_THINKING_LEVEL", profile.default_thinking_level)

    return GeminiSettings(
        enabled=enabled,
        api_key=api_key,
        base_url=base_url or DEFAULT_GEMINI_BASE_URL,
        model=model or DEFAULT_GEMINI_MODEL,
        timeout=max(timeout, 1.0),
        temperature=max(0.0, temperature),
        max_output_tokens=max(64, min(profile.output_token_limit, max_output_tokens)),
        thinking_budget=_normalize_thinking_budget(default_thinking_budget, profile),
        thinking_level=_normalize_thinking_level(default_thinking_level, profile),
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
    thinking_budget: int | None = None,
    thinking_level: str | None = None,
) -> GeminiSettings:
    """Return settings with explicit UI/runtime overrides applied."""
    api_key_override = (api_key or "").strip()
    selected_model = (model or settings.model).strip() or DEFAULT_GEMINI_MODEL
    profile = gemini_profile_for_model(selected_model)
    output_tokens = max_output_tokens if max_output_tokens is not None else settings.max_output_tokens
    budget = thinking_budget if thinking_budget is not None else settings.thinking_budget
    level = thinking_level if thinking_level is not None else settings.thinking_level
    return GeminiSettings(
        enabled=settings.enabled,
        api_key=api_key_override or settings.api_key,
        base_url=(base_url or settings.base_url).strip() or DEFAULT_GEMINI_BASE_URL,
        model=selected_model,
        timeout=max(float(timeout if timeout is not None else settings.timeout), 1.0),
        temperature=max(float(temperature if temperature is not None else settings.temperature), 0.0),
        max_output_tokens=max(64, min(profile.output_token_limit, int(output_tokens))),
        thinking_budget=_normalize_thinking_budget(budget, profile),
        thinking_level=_normalize_thinking_level(level, profile),
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
    profile = gemini_profile_for_model(settings.model)
    if profile.thinking_control == "budget" and settings.thinking_budget is not None:
        payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": settings.thinking_budget}
    elif profile.thinking_control == "level" and settings.thinking_level:
        payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": settings.thinking_level}
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
