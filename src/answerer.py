"""Grounded Korean answer generation for retrieved school notices."""

from __future__ import annotations

import os
import re
from typing import Any, Mapping, Sequence

from src.gemini_client import GeminiError, generate_with_gemini, load_gemini_settings, with_gemini_overrides
from src.ollama_client import OllamaError, generate_with_ollama, load_ollama_settings, with_ollama_overrides

SAFE_UNKNOWN_ANSWER = "수집된 공지 데이터에서 확인되지 않음: 관련 공지를 찾지 못했습니다. 학교 공식 공지 게시판에서 최신 내용을 다시 확인해 주세요."
GROUNDING_SYSTEM_PROMPT = (
    "당신은 학교 공지 RAG 챗봇입니다. 제공된 근거에 있는 사실만 사용하세요. "
    "근거에 없는 일정, 금액, 장소, 절차는 추측하지 말고 '수집된 공지 데이터에서 확인되지 않음'이라고 답하세요. "
    "근거에 답이 있으면 미확인 문구를 덧붙이지 마세요. "
    "답변은 한국어로 간결하게 작성하세요."
)
OLLAMA_SYSTEM_PROMPT = GROUNDING_SYSTEM_PROMPT


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _clip(value: Any, max_chars: int = 300) -> str:
    text = _clean(value)
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "…"


def _clean_snippet(value: Any) -> str:
    text = _clean(value)
    return "" if not re.search(r"[0-9A-Za-z가-힣]", text) else text


def _source_line(source: Mapping[str, Any]) -> str:
    title = _clean(source.get("title")) or _clean(source.get("source_board")) or "제목 없음"
    date = _clean(source.get("date")) or "날짜 미상"
    board = _clean(source.get("source_board")) or _clean(source.get("category")) or "공지"
    return f"- **{title}** ({date}, {board})"


def _evidence_snippets(results: Sequence[Mapping[str, Any]], max_sources: int = 3) -> list[str]:
    return [_clean_snippet(source.get("snippet")) for source in results[:max_sources] if _clean_snippet(source.get("snippet"))]


def _confidence_for_score(score: float) -> str:
    return "high" if score >= 0.3 else "medium"


def is_confident(results: Sequence[Mapping[str, Any]], min_score: float = 0.18) -> bool:
    if not results:
        return False
    try:
        return float(results[0].get("score", 0.0)) >= min_score
    except (TypeError, ValueError):
        return False


def build_extractive_answer(query: str, results: Sequence[Mapping[str, Any]], max_sources: int = 3) -> dict[str, Any]:
    """Build a citation-first answer using only retrieved notice snippets."""
    if not is_confident(results):
        return {
            "answer": SAFE_UNKNOWN_ANSWER,
            "sources": [],
            "evidence_snippets": [],
            "used_llm": False,
            "confidence": "low",
        }

    selected = list(results[:max_sources])
    summary_bits: list[str] = ["수집된 공지 데이터 기준으로 확인했어요.", "", "**요약**"]
    evidence: list[str] = []
    for source in selected:
        title = _clean(source.get("title")) or "관련 공지"
        date = _clean(source.get("date")) or "날짜 미상"
        snippet = _clean_snippet(source.get("snippet"))
        if snippet:
            summary_bits.append(f"- **{title}** ({date})  \n  {snippet}")
            evidence.append(snippet)
        else:
            summary_bits.append(f"- **{title}** ({date})  \n  상세 내용은 아래 출처 카드에서 확인해 주세요.")

    first_score = float(selected[0].get("score", 0.0))
    answer = "\n".join(
        [
            f"**질문:** {_clip(query)}",
            "",
            *summary_bits,
        ]
    )
    return {
        "answer": answer,
        "sources": selected,
        "evidence_snippets": evidence,
        "used_llm": False,
        "confidence": _confidence_for_score(first_score),
    }


def build_llm_prompt(query: str, results: Sequence[Mapping[str, Any]]) -> str:
    """Create a strict grounded prompt containing only retrieved evidence."""
    evidence_blocks = []
    for idx, source in enumerate(results, start=1):
        evidence_blocks.append(
            "\n".join(
                [
                    f"[근거 {idx}]",
                    f"title: {_clean(source.get('title'))}",
                    f"date: {_clean(source.get('date'))}",
                    f"url: {_clean(source.get('url'))}",
                    f"snippet: {_clean_snippet(source.get('snippet')) or '(스니펫 없음 — 제목/날짜/URL을 근거로 사용)'}",
                ]
            )
        )
    return "\n\n".join(
        [
            "당신은 학교 공지 RAG 챗봇입니다. 아래 근거에 없는 내용은 추측하지 마세요.",
            "답변은 한국어로 작성하고, 불확실하면 '수집된 공지 데이터에서 확인되지 않음'이라고 말하세요.",
            "근거 항목이 1개 이상 있으면 제목, 날짜, 게시판/URL을 근거로 관련 공지 목록을 답하세요.",
            "'최근' 또는 '최신' 질문은 근거의 date를 보고 최신 항목을 먼저 요약하세요.",
            "근거에 답이 명시되어 있으면 '수집된 공지 데이터에서 확인되지 않음' 문구를 덧붙이지 마세요.",
            "응답 형식은 '**요약**' 다음에 '- **공지명** (날짜): 한 줄 요약' 목록으로 작성하세요.",
            "답변 본문에는 URL, 원문 링크, '링크:' 문구를 쓰지 마세요. URL은 별도 출처 카드에서만 보여줍니다.",
            "title, date, url, snippet 같은 필드명은 그대로 출력하지 마세요.",
            "출처/근거 목록은 별도 카드에서 보여주므로 답변에는 핵심 요약만 작성하세요.",
            f"질문: {_clip(query, max_chars=500)}",
            "근거:\n" + "\n\n".join(evidence_blocks),
        ]
    )


def _normalize_answer_inputs(
    query: str | None,
    retrieved_results: Sequence[Mapping[str, Any]] | None,
    *,
    question: str | None,
    sources: Sequence[Mapping[str, Any]] | None,
) -> tuple[str, Sequence[Mapping[str, Any]]]:
    """Accept both backend and Streamlit-friendly argument names."""
    normalized_query = _clean(query if query is not None else question)
    normalized_results = retrieved_results if retrieved_results is not None else sources
    return normalized_query, list(normalized_results or [])


def _legacy_prompt_only_requested(use_llm: bool | None, provider: str | None) -> bool:
    """Preserve the former OpenAI-key behavior without making a network call."""
    provider_name = (provider or os.getenv("KD_NOTICE_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "").strip().lower()
    if provider_name and provider_name != "openai":
        return False
    return use_llm is None and os.getenv("OPENAI_API_KEY") is not None


def _looks_like_unknown(answer: str) -> bool:
    return "수집된 공지 데이터에서 확인되지 않음" in _clean(answer)


def _remove_answer_links(answer: str) -> str:
    """Remove raw URLs/link labels from model-generated answer text."""
    text = re.sub(r"\s*링크\s*:\s*https?://\S+", "", answer)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _provider_name(provider: str | None) -> str:
    return (provider or os.getenv("KD_NOTICE_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "").strip().lower()


def answer_question(
    query: str | None = None,
    retrieved_results: Sequence[Mapping[str, Any]] | None = None,
    *,
    question: str | None = None,
    sources: Sequence[Mapping[str, Any]] | None = None,
    min_score: float = 0.18,
    use_llm: bool | None = None,
    llm_provider: str | None = None,
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    ollama_timeout: float | None = None,
    ollama_num_predict: int | None = None,
    gemini_model: str | None = None,
    gemini_api_key: str | None = None,
    gemini_base_url: str | None = None,
    gemini_timeout: float | None = None,
    gemini_max_output_tokens: int | None = None,
) -> dict[str, Any]:
    """Return a grounded answer payload for the UI.

    The default path remains deterministic and extractive.  When explicitly
    enabled via ``use_llm=True`` with an explicit provider, or via
    ``KD_NOTICE_LLM_PROVIDER=ollama|gemini``, the answer layer sends only the
    retrieved evidence prompt to the selected model and falls back to the
    extractive answer on any provider failure.
    """
    normalized_query, normalized_results = _normalize_answer_inputs(
        query,
        retrieved_results,
        question=question,
        sources=sources,
    )

    if not is_confident(normalized_results, min_score=min_score):
        return {
            "answer": SAFE_UNKNOWN_ANSWER,
            "sources": [],
            "evidence_snippets": [],
            "used_llm": False,
            "confidence": "low",
        }

    provider_name = _provider_name(llm_provider)
    selected = list(normalized_results[:3])

    gemini_settings = with_gemini_overrides(
        load_gemini_settings(use_llm=use_llm, provider=llm_provider),
        model=gemini_model,
        api_key=gemini_api_key,
        base_url=gemini_base_url,
        timeout=gemini_timeout,
        max_output_tokens=gemini_max_output_tokens,
    )
    if provider_name == "gemini" and gemini_settings.enabled:
        try:
            generated = generate_with_gemini(
                build_llm_prompt(normalized_query, selected),
                settings=gemini_settings,
                system=GROUNDING_SYSTEM_PROMPT,
            )
            generated_text = _remove_answer_links(_clip(generated["text"], max_chars=4000))
            if _looks_like_unknown(generated_text):
                payload = build_extractive_answer(normalized_query, normalized_results)
                payload["llm_provider"] = "gemini"
                payload["llm_status"] = "gemini_unknown_fallback"
                payload["llm_model"] = generated["model"]
                return payload
            first_score = float(selected[0].get("score", 0.0))
            return {
                "answer": generated_text,
                "sources": selected,
                "evidence_snippets": _evidence_snippets(selected),
                "used_llm": True,
                "llm_provider": "gemini",
                "llm_status": "gemini_generated",
                "llm_model": generated["model"],
                "confidence": _confidence_for_score(first_score),
            }
        except (GeminiError, OSError) as exc:
            payload = build_extractive_answer(normalized_query, normalized_results)
            payload["llm_provider"] = "gemini"
            payload["llm_status"] = "gemini_unavailable_fallback"
            payload["llm_error"] = _clip(str(exc), max_chars=240)
            return payload

    settings = with_ollama_overrides(
        load_ollama_settings(use_llm=use_llm, provider=llm_provider),
        model=ollama_model,
        base_url=ollama_base_url,
        timeout=ollama_timeout,
        num_predict=ollama_num_predict,
    )
    if settings.enabled:
        try:
            generated = generate_with_ollama(
                build_llm_prompt(normalized_query, selected),
                settings=settings,
                system=OLLAMA_SYSTEM_PROMPT,
            )
            generated_text = _remove_answer_links(_clip(generated["text"], max_chars=4000))
            if _looks_like_unknown(generated_text):
                payload = build_extractive_answer(normalized_query, normalized_results)
                payload["llm_provider"] = "ollama"
                payload["llm_status"] = "ollama_unknown_fallback"
                payload["llm_model"] = generated["model"]
                return payload
            first_score = float(selected[0].get("score", 0.0))
            return {
                "answer": generated_text,
                "sources": selected,
                "evidence_snippets": _evidence_snippets(selected),
                "used_llm": True,
                "llm_provider": "ollama",
                "llm_status": "ollama_generated",
                "llm_model": generated["model"],
                "confidence": _confidence_for_score(first_score),
            }
        except (OllamaError, OSError) as exc:
            payload = build_extractive_answer(normalized_query, normalized_results)
            payload["llm_provider"] = "ollama"
            payload["llm_status"] = "ollama_unavailable_fallback"
            payload["llm_error"] = _clip(str(exc), max_chars=240)
            return payload

    if _legacy_prompt_only_requested(use_llm, llm_provider):
        payload = build_extractive_answer(normalized_query, normalized_results)
        payload["llm_prompt"] = build_llm_prompt(normalized_query, normalized_results[:3])
        payload["used_llm"] = False
        payload["llm_status"] = "prompt_prepared_only"
        return payload

    return build_extractive_answer(normalized_query, normalized_results)
