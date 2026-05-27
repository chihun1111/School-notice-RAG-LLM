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
CONFIG_PATH = Path("config") / "boards.yaml"
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


def configured_max_pages(default: int = 3) -> int:
    """Read the configured board-page crawl limit for the refresh UI."""
    try:
        import yaml

        with CONFIG_PATH.open(encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        value = int((config.get("crawler") or {}).get("max_pages_per_board", default))
    except Exception:
        value = default
    return max(1, value)


def run_dataset_refresh(max_pages: int | None = None) -> tuple[bool, str]:
    """Run the explicit dataset builder; chat requests never call this."""
    if not BUILD_SCRIPT.exists():
        return False, f"데이터셋 빌드 스크립트를 찾을 수 없습니다: {BUILD_SCRIPT}"
    command = [sys.executable, str(BUILD_SCRIPT)]
    if max_pages is not None:
        command.extend(["--max-pages", str(max(1, int(max_pages)))])
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=600,
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


def build_answer(
    question: str,
    rows: list[dict[str, str]],
    *,
    use_llm: bool | None = None,
    llm_provider: str | None = None,
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    ollama_timeout: float | None = None,
    ollama_num_predict: int | None = None,
    gemini_model: str | None = None,
    gemini_api_key: str | None = None,
    gemini_timeout: float | None = None,
    gemini_max_output_tokens: int | None = None,
) -> tuple[str, list[Source]]:
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
            payload = answer_fn(
                query=question,
                retrieved_results=[source.__dict__ for source in sources],
                use_llm=use_llm,
                llm_provider=llm_provider,
                ollama_model=ollama_model,
                ollama_base_url=ollama_base_url,
                ollama_timeout=ollama_timeout,
                ollama_num_predict=ollama_num_predict,
                gemini_model=gemini_model,
                gemini_api_key=gemini_api_key,
                gemini_timeout=gemini_timeout,
                gemini_max_output_tokens=gemini_max_output_tokens,
            )
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


def render_thinking_motion(target: Any) -> None:
    """Render a lightweight animated thinking indicator while RAG runs."""
    target.markdown(
        """
        <style>
          .thinking-card {
            display: inline-flex;
            align-items: center;
            gap: 0.65rem;
            padding: 0.75rem 1rem;
            margin: 0.25rem 0 0.75rem 0;
            border-radius: 999px;
            background: linear-gradient(90deg, rgba(79, 70, 229, 0.10), rgba(14, 165, 233, 0.12));
            border: 1px solid rgba(79, 70, 229, 0.18);
            color: #1f2937;
            font-weight: 600;
          }
          .thinking-dots {
            display: inline-flex;
            gap: 0.25rem;
          }
          .thinking-dots span {
            width: 0.42rem;
            height: 0.42rem;
            border-radius: 999px;
            background: #4f46e5;
            animation: thinking-bounce 0.95s infinite ease-in-out;
          }
          .thinking-dots span:nth-child(2) { animation-delay: 0.14s; background: #2563eb; }
          .thinking-dots span:nth-child(3) { animation-delay: 0.28s; background: #0891b2; }
          @keyframes thinking-bounce {
            0%, 80%, 100% { transform: translateY(0); opacity: 0.45; }
            40% { transform: translateY(-0.32rem); opacity: 1; }
          }
        </style>
        <div class="thinking-card" role="status" aria-live="polite">
          <span>근거 검색하고 생각 중</span>
          <span class="thinking-dots"><span></span><span></span><span></span></span>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
        crawl_pages = st.number_input(
            "보드별 크롤링 페이지 수",
            min_value=1,
            max_value=10,
            value=configured_max_pages(),
            step=1,
            help="데이터셋 새로고침 때만 적용됩니다. 채팅 중에는 크롤링하지 않습니다.",
        )
        if st.button("데이터셋 새로고침", help="명시적으로 scripts/build_dataset.py를 실행합니다."):
            with st.spinner("공지 데이터셋을 갱신하는 중..."):
                ok, output = run_dataset_refresh(max_pages=int(crawl_pages))
            (st.success if ok else st.error)("데이터셋 빌드 완료" if ok else "데이터셋 빌드 실패")
            st.code(output[-4000:] if output else "no output")
            st.rerun()

        st.divider()
        st.header("AI 답변 생성")
        use_llm = False
        llm_provider = None
        ollama_model = None
        ollama_base_url = None
        ollama_timeout = None
        ollama_num_predict = None
        gemini_model = None
        gemini_api_key = None
        gemini_timeout = None
        gemini_max_output_tokens = None
        try:
            from src.gemini_client import load_gemini_settings
            from src.ollama_client import list_ollama_models, load_ollama_settings

            ollama_settings = load_ollama_settings()
            gemini_settings = load_gemini_settings()
            if gemini_settings.enabled:
                default_provider_label = "Gemini API"
            elif ollama_settings.enabled:
                default_provider_label = "Ollama"
            else:
                default_provider_label = "추출형만"

            with st.expander("⚙️ 모델 설정", expanded=True):
                provider_label = st.selectbox(
                    "답변 생성 방식",
                    options=["추출형만", "Ollama", "Gemini API"],
                    index=["추출형만", "Ollama", "Gemini API"].index(default_provider_label),
                    help="LLM은 검색된 공지/학사일정 근거만 받아 문장화합니다. 실패하면 추출형 답변으로 자동 전환됩니다.",
                )
                use_llm = provider_label != "추출형만"
                llm_provider = {"Ollama": "ollama", "Gemini API": "gemini"}.get(provider_label)

                if provider_label == "Ollama":
                    ollama_base_url = st.text_input(
                        "Ollama URL",
                        value=ollama_settings.base_url,
                        help="기본값은 로컬 Ollama 서버(http://localhost:11434)입니다.",
                    )
                    installed_models = list_ollama_models(ollama_base_url)
                    default_model = ollama_settings.model
                    if installed_models:
                        if default_model not in installed_models:
                            installed_models = [default_model, *installed_models]
                        selected_model = st.selectbox(
                            "설치된 Ollama 모델",
                            options=installed_models,
                            index=installed_models.index(default_model),
                            help="Ollama에 설치된 모델 목록입니다. 아래 입력칸에서 직접 다른 태그로 수정할 수도 있습니다.",
                        )
                    else:
                        selected_model = default_model
                        st.caption("Ollama 모델 목록을 읽지 못했습니다. 모델명을 직접 입력하세요.")
                    ollama_model = st.text_input("Ollama 모델명 직접 수정", value=selected_model)
                    with st.expander("Ollama 고급 설정"):
                        ollama_num_predict = st.number_input(
                            "Ollama 최대 생성 토큰",
                            min_value=64,
                            max_value=2048,
                            value=int(ollama_settings.num_predict),
                            step=64,
                        )
                        ollama_timeout = st.number_input(
                            "Ollama 응답 제한 시간(초)",
                            min_value=5,
                            max_value=300,
                            value=int(ollama_settings.timeout),
                            step=5,
                        )
                    st.caption(f"현재 사용 모델: `{ollama_model}`")

                elif provider_label == "Gemini API":
                    gemini_model = st.text_input(
                        "Gemini 모델명",
                        value=gemini_settings.model,
                        help="예: gemini-2.5-flash. 환경변수 KD_NOTICE_GEMINI_MODEL/GEMINI_MODEL로도 설정할 수 있습니다.",
                    )
                    gemini_api_key = st.text_input(
                        "Gemini API 키",
                        value="",
                        type="password",
                        placeholder="비워두면 GEMINI_API_KEY / GOOGLE_API_KEY 환경변수 사용",
                        help="입력한 키는 현재 실행 중인 요청에만 전달하고 파일에 저장하지 않습니다.",
                    )
                    with st.expander("Gemini 고급 설정"):
                        gemini_max_output_tokens = st.number_input(
                            "Gemini 최대 생성 토큰",
                            min_value=64,
                            max_value=4096,
                            value=int(gemini_settings.max_output_tokens),
                            step=64,
                        )
                        gemini_timeout = st.number_input(
                            "Gemini 응답 제한 시간(초)",
                            min_value=5,
                            max_value=300,
                            value=int(gemini_settings.timeout),
                            step=5,
                        )
                    key_state = "입력 키 사용" if gemini_api_key else ("환경변수 키 사용" if gemini_settings.api_key else "키 없음")
                    st.caption(f"현재 사용 모델: `{gemini_model}` · API 키: {key_state}")
                else:
                    st.caption("LLM 없이 검색된 근거를 추출형으로 답변합니다.")
        except Exception:
            use_llm = False
            llm_provider = None
            st.caption("AI 모델 설정을 읽지 못해 추출형 답변만 사용합니다.")

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
            motion_slot = st.empty()
            with st.spinner("공지 데이터에서 근거를 검색하는 중..."):
                try:
                    render_thinking_motion(motion_slot)
                    answer, sources = build_answer(
                        question,
                        rows,
                        use_llm=use_llm,
                        llm_provider=llm_provider,
                        ollama_model=ollama_model,
                        ollama_base_url=ollama_base_url,
                        ollama_timeout=ollama_timeout,
                        ollama_num_predict=ollama_num_predict,
                        gemini_model=gemini_model,
                        gemini_api_key=gemini_api_key,
                        gemini_timeout=gemini_timeout,
                        gemini_max_output_tokens=gemini_max_output_tokens,
                    )
                finally:
                    motion_slot.empty()
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
