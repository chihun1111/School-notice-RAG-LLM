"""Grounded Korean answer generation for retrieved school notices."""

from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

SAFE_UNKNOWN_ANSWER = "수집된 공지 데이터에서 확인되지 않음: 관련 공지를 찾지 못했습니다. 학교 공식 공지 게시판에서 최신 내용을 다시 확인해 주세요."


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _clip(value: Any, max_chars: int = 300) -> str:
    text = _clean(value)
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "…"


def _source_line(source: Mapping[str, Any]) -> str:
    title = _clean(source.get("title")) or _clean(source.get("source_board")) or "제목 없음"
    date = _clean(source.get("date")) or "날짜 미상"
    board = _clean(source.get("source_board")) or _clean(source.get("category")) or "공지"
    url = _clean(source.get("url"))
    return f"- {title} ({date}, {board})" + (f"\n  {url}" if url else "")


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
    summary_bits: list[str] = []
    evidence: list[str] = []
    for source in selected:
        title = _clean(source.get("title")) or "관련 공지"
        date = _clean(source.get("date")) or "날짜 미상"
        snippet = _clean(source.get("snippet"))
        if snippet:
            summary_bits.append(f"'{title}' 공지({date})에 따르면 {snippet}")
            evidence.append(snippet)
        else:
            summary_bits.append(f"'{title}' 공지({date})를 확인해 주세요.")

    answer = "\n".join(
        [
            f"질문: {_clip(query)}",
            "수집된 공지 데이터 기준으로 확인한 내용입니다.",
            " ".join(summary_bits),
            "\n출처:\n" + "\n".join(_source_line(source) for source in selected),
        ]
    )
    return {
        "answer": answer,
        "sources": selected,
        "evidence_snippets": evidence,
        "used_llm": False,
        "confidence": "high" if float(selected[0].get("score", 0.0)) >= 0.3 else "medium",
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
                    f"snippet: {_clean(source.get('snippet'))}",
                ]
            )
        )
    return "\n\n".join(
        [
            "당신은 학교 공지 RAG 챗봇입니다. 아래 근거에 없는 내용은 추측하지 마세요.",
            "답변은 한국어로 작성하고, 불확실하면 '수집된 공지 데이터에서 확인되지 않음'이라고 말하세요.",
            f"질문: {_clip(query, max_chars=500)}",
            "근거:\n" + "\n\n".join(evidence_blocks),
        ]
    )


def answer_question(
    query: str,
    retrieved_results: Sequence[Mapping[str, Any]],
    *,
    min_score: float = 0.18,
    use_llm: bool | None = None,
) -> dict[str, Any]:
    """Return a grounded answer payload for the UI.

    The MVP is safe by default: if no API key is configured, it returns an
    extractive answer. LLM use can be layered on later with the strict prompt
    from ``build_llm_prompt`` without changing the UI contract.
    """
    if not is_confident(retrieved_results, min_score=min_score):
        return {
            "answer": SAFE_UNKNOWN_ANSWER,
            "sources": [],
            "evidence_snippets": [],
            "used_llm": False,
            "confidence": "low",
        }

    should_use_llm = (os.getenv("OPENAI_API_KEY") is not None) if use_llm is None else use_llm
    if should_use_llm:
        # Deliberately do not call a network API in the deterministic MVP path.
        # The prompt is exposed for future integration and for test visibility.
        payload = build_extractive_answer(query, retrieved_results)
        payload["llm_prompt"] = build_llm_prompt(query, retrieved_results[:3])
        payload["used_llm"] = False
        payload["llm_status"] = "prompt_prepared_only"
        return payload

    return build_extractive_answer(query, retrieved_results)
