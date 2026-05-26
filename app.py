"""Streamlit demo UI for the school notice RAG chatbot.

The UI is intentionally dependency-light at import time so it can be syntax-checked
before every backend worker has landed its modules. At runtime it prefers the
project RAG/answerer modules when present and falls back to a deterministic
extractive search so the competition demo still shows safe grounded behavior.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATA_DIR = Path("data")
CSV_PATH = DATA_DIR / "notices.csv"
JSONL_PATH = DATA_DIR / "notices.jsonl"
BUILD_SCRIPT = Path("scripts") / "build_dataset.py"
UNKNOWN_MESSAGE = "수집된 공지 데이터에서 확인되지 않음"
RECOMMENDED_QUESTIONS = [
    "장학금 신청 관련 공지를 알려줘",
    "학사 일정이나 수강신청 관련 공지가 있어?",
    "취업 또는 채용 관련 최근 공지를 찾아줘",
    "학생지원 프로그램 공지를 요약해줘",
    "최근 공지 중 중요한 내용을 알려줘",
]
REQUIRED_FIELDS = ["title", "category", "date", "url", "source_board", "content_or_snippet"]
GENERIC_QUERY_TOKENS = {
    "공지",
    "공지가",
    "관련",
    "알려줘",
    "요약해줘",
    "최근",
    "있어",
    "있나요",
    "찾아줘",
}


@dataclass(frozen=True)
class Source:
    title: str
    url: str
    date: str = ""
    category: str = ""
    source_board: str = ""
    snippet: str = ""
    score: float = 0.0


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clip_text(value: Any, max_chars: int = 300) -> str:
    text = _as_text(value)
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "…"


def _record_to_source(record: dict[str, Any]) -> Source:
    return Source(
        title=_as_text(record.get("title")) or "제목 없음",
        url=_as_text(record.get("url")),
        date=_as_text(record.get("date")),
        category=_as_text(record.get("category")),
        source_board=_as_text(record.get("source_board")),
        snippet=_as_text(record.get("content_or_snippet") or record.get("snippet")),
        score=float(record.get("score") or 0.0),
    )


def load_notices() -> list[dict[str, str]]:
    """Load notice records from CSV first, then JSONL as a fallback."""
    if CSV_PATH.exists():
        with CSV_PATH.open(newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if JSONL_PATH.exists():
        rows: list[dict[str, str]] = []
        with JSONL_PATH.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    return []


def dataset_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if rows and not any(_as_text(row.get(field)) for row in rows)]
    return {
        "count": len(rows),
        "csv_exists": CSV_PATH.exists(),
        "jsonl_exists": JSONL_PATH.exists(),
        "missing_fields": missing,
    }


def run_dataset_refresh() -> tuple[bool, str]:
    """Run the explicit dataset builder; chat requests never call this."""
    if not BUILD_SCRIPT.exists():
        return False, f"데이터셋 빌드 스크립트를 찾을 수 없습니다: {BUILD_SCRIPT}"
    completed = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT)],
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
    return completed.returncode == 0, output or "빌드 스크립트가 출력 없이 종료되었습니다."


def _keyword_tokens(query: str) -> set[str]:
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in query)
    return {token for token in normalized.split() if len(token) >= 2 and token not in GENERIC_QUERY_TOKENS}


def fallback_retrieve(question: str, rows: list[dict[str, str]], limit: int = 5) -> list[Source]:
    """Deterministic Korean-friendly keyword fallback for UI resilience."""
    tokens = _keyword_tokens(question)
    if not tokens:
        return []

    ranked: list[tuple[float, dict[str, str]]] = []
    for row in rows:
        haystack_parts = [row.get(field, "") for field in REQUIRED_FIELDS]
        haystack = " ".join(_as_text(part).lower() for part in haystack_parts)
        score = 0.0
        for token in tokens:
            if token in haystack:
                score += 1.0
                if token in _as_text(row.get("title")).lower():
                    score += 1.5
                if token in _as_text(row.get("category")).lower():
                    score += 0.75
        if score > 0:
            ranked.append((score, row))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [_record_to_source({**row, "score": score}) for score, row in ranked[:limit]]


def retrieve_sources(question: str, rows: list[dict[str, str]]) -> list[Source]:
    """Prefer backend RAG modules, falling back to local keyword retrieval."""
    backend_available = False
    try:
        import importlib

        rag_module = importlib.import_module("src.rag")
        search_notices = getattr(rag_module, "search_notices", None)
        HybridRetriever = getattr(rag_module, "HybridRetriever", None)
        RAGRetriever = getattr(rag_module, "RAGRetriever", None)
        backend_available = any(item is not None for item in (search_notices, HybridRetriever, RAGRetriever))
    except Exception:
        HybridRetriever = RAGRetriever = search_notices = None  # type: ignore

    candidates: Any = None
    try:
        if search_notices is not None:
            candidates = search_notices(rows, question, top_k=5)
        elif HybridRetriever is not None:
            candidates = HybridRetriever(rows).search(question, top_k=5)
        elif RAGRetriever is not None:
            candidates = RAGRetriever(rows).search(question, top_k=5)
    except Exception:
        candidates = None

    if candidates is not None:
        return [_record_to_source(dict(item)) for item in candidates]
    if backend_available:
        return []
    return fallback_retrieve(question, rows)


def build_extractive_answer(question: str, sources: list[Source]) -> str:
    if not sources or sources[0].score <= 0:
        return f"{UNKNOWN_MESSAGE}. 질문과 관련된 공지를 찾을 수 없어서 답변을 생성하지 않았습니다."
    lead = sources[0]
    snippet = lead.snippet[:220] + ("…" if len(lead.snippet) > 220 else "")
    return (
        f"질문 '{_clip_text(question)}'와 관련해 가장 근거가 높은 공지는 '{lead.title}'입니다. "
        f"작성일은 {lead.date or '확인 필요'}이며, {lead.source_board or lead.category or '공지 게시판'}에서 확인된 내용입니다. "
        f"근거: {snippet or '상세 내용은 원문 링크를 확인하세요.'}"
    )


def build_answer(question: str, rows: list[dict[str, str]]) -> tuple[str, list[Source]]:
    sources = retrieve_sources(question, rows)
    try:
        import importlib

        answerer_module = importlib.import_module("src.answerer")
        answer_question = getattr(answerer_module, "answer_question", None)
        generate_answer = getattr(answerer_module, "generate_answer", None)
    except Exception:
        answer_question = generate_answer = None  # type: ignore

    for answer_fn in (answer_question, generate_answer):
        if answer_fn is None:
            continue
        try:
            payload = answer_fn(question=question, sources=[source.__dict__ for source in sources])
            if isinstance(payload, dict):
                answer = _as_text(payload.get("answer"))
                payload_sources = payload.get("sources") or payload.get("evidence")
                if payload_sources:
                    sources = [_record_to_source(dict(item)) for item in payload_sources]
                if answer:
                    return answer, sources
            elif _as_text(payload):
                return _as_text(payload), sources
        except Exception:
            continue

    return build_extractive_answer(question, sources), sources


def render_source_card(st: Any, source: Source, index: int) -> None:
    title = f"근거 {index}: {source.title}"
    with st.expander(title, expanded=index == 1):
        meta = " · ".join(part for part in [source.date, source.category, source.source_board] if part)
        if meta:
            st.caption(meta)
        if source.url:
            st.markdown(f"[원문 링크]({source.url})")
        st.write(source.snippet or "본문 스니펫이 없어 원문 확인이 필요합니다.")
        if source.score:
            st.caption(f"retrieval score: {source.score:.2f}")


def render_app() -> None:
    import streamlit as st

    st.set_page_config(page_title="학교 공지 RAG 챗봇", page_icon="🎓", layout="wide")
    st.title("🎓 학교 공지 게시판 RAG AI 챗봇")
    st.caption("수집된 공지 데이터만 근거로 답변하고, 출처/날짜/스니펫을 함께 보여주는 데모 UI입니다.")

    rows = load_notices()
    summary = dataset_summary(rows)

    with st.sidebar:
        st.header("데이터셋 상태")
        st.metric("공지 수", summary["count"])
        st.write(f"CSV: {'있음' if summary['csv_exists'] else '없음'}")
        st.write(f"JSONL: {'있음' if summary['jsonl_exists'] else '없음'}")
        if summary["missing_fields"]:
            st.warning("누락 필드: " + ", ".join(summary["missing_fields"]))
        if st.button("데이터셋 새로고침", help="명시적으로 scripts/build_dataset.py를 실행합니다."):
            with st.spinner("공지 데이터셋을 갱신하는 중..."):
                ok, output = run_dataset_refresh()
            (st.success if ok else st.error)("데이터셋 빌드 완료" if ok else "데이터셋 빌드 실패")
            st.code(output[-4000:] if output else "no output")
            st.rerun()

    if not rows:
        st.info("아직 수집된 공지 데이터가 없습니다. 사이드바의 데이터셋 새로고침을 실행하거나 `python scripts/build_dataset.py`를 먼저 실행하세요.")

    st.subheader("추천 데모 질문")
    selected_question = None
    columns = st.columns(2)
    for index, question in enumerate(RECOMMENDED_QUESTIONS):
        if columns[index % 2].button(question, key=f"demo-question-{index}"):
            selected_question = question

    typed_question = st.chat_input("공지에 대해 질문하세요. 예: 장학금 신청 기간 알려줘")
    question = typed_question or selected_question

    if question:
        st.chat_message("user").write(question)
        with st.chat_message("assistant"):
            with st.spinner("공지 데이터에서 근거를 검색하는 중..."):
                answer, sources = build_answer(question, rows)
            st.markdown("### 답변")
            if answer.startswith(UNKNOWN_MESSAGE):
                st.warning(answer)
            else:
                st.write(answer)
            st.markdown("### 출처 및 근거")
            if sources:
                for index, source in enumerate(sources, start=1):
                    render_source_card(st, source, index)
            else:
                st.caption("표시할 근거 공지가 없습니다.")

    st.divider()
    st.caption("안전장치: 채팅 중 자동 크롤링 없음 · 낮은 관련성 질문은 미확인 답변 반환 · 실제 공지 링크와 스니펫 우선 표시")


if __name__ == "__main__":
    render_app()
