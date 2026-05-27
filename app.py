"""Streamlit demo UI for the school notice RAG chatbot.

The UI is intentionally dependency-light at import time so it can be syntax-checked
before every backend worker has landed its modules. At runtime it prefers the
project RAG/answerer modules when present and falls back to a deterministic
extractive search so the competition demo still shows safe grounded behavior.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

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
CRAWL_SOURCE_GROUPS = {
    "boards": "공지 게시판",
    "schedules": "학사일정",
}
ALLOWED_CRAWL_HOSTS = {"www.kduniv.ac.kr", "kduniv.ac.kr"}
DEFAULT_CRAWLER_OPTIONS = {
    "max_pages_per_board": 3,
    "request_timeout_seconds": 12,
    "polite_delay_seconds": 0.25,
    "user_agent": "KDUniversityNoticeRAGDemo/0.1 (+local competition demo; public pages only)",
}
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


def _load_yaml_module() -> Any:
    import yaml

    return yaml


def _normal_source_item(item: dict[str, Any], *, fallback_id: str, fallback_label: str, fallback_category: str) -> dict[str, str]:
    return {
        "id": _as_text(item.get("id")) or fallback_id,
        "label": _as_text(item.get("label")) or fallback_label,
        "category": _as_text(item.get("category")) or fallback_category,
        "url": _as_text(item.get("url")),
    }


def load_crawl_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load editable crawler sources and crawler options from YAML."""
    yaml = _load_yaml_module()
    raw: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    return load_crawl_config_from_dict(raw)


def save_crawl_config(config: dict[str, Any], config_path: Path = CONFIG_PATH) -> None:
    """Persist editable crawler sources to YAML for future dataset refreshes."""
    yaml = _load_yaml_module()
    payload = {
        "boards": [
            {key: _as_text(source.get(key)) for key in ("id", "label", "category", "url")}
            for source in config.get("boards", [])
            if _as_text(source.get("url"))
        ],
        "schedules": [
            {key: _as_text(source.get(key)) for key in ("id", "label", "category", "url")}
            for source in config.get("schedules", [])
            if _as_text(source.get("url"))
        ],
        "crawler": {**DEFAULT_CRAWLER_OPTIONS, **(config.get("crawler", {}) or {})},
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        handle.write("# Editable crawler sources for the school notice RAG demo.\n")
        handle.write("# Chat requests never crawl automatically; use the settings dialog refresh button or scripts/build_dataset.py.\n")
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)


def _canonical_source_url(url: str) -> str:
    parsed = urlparse(_as_text(url))
    return parsed._replace(fragment="").geturl().rstrip("/")


def _validate_crawl_source_url(url: str, group: str) -> str:
    value = _as_text(url)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL은 http:// 또는 https:// 형식이어야 합니다.")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_CRAWL_HOSTS:
        raise ValueError("현재 데모 크롤러는 경동대학교 공개 URL(www.kduniv.ac.kr)만 저장할 수 있습니다.")
    query = parse_qs(parsed.query)
    if not query.get("mCode"):
        raise ValueError("경동대학교 URL의 mCode 파라미터가 필요합니다.")
    path = parsed.path
    mode = (query.get("mode") or [""])[0].lower()
    if group == "boards":
        if "Board.do" not in path or mode == "view":
            raise ValueError("공지 게시판은 경동대학교 Board.do 목록 URL을 입력하세요. 상세글(mode=view) URL은 사용할 수 없습니다.")
    elif group == "schedules":
        if "ScheduleMgr" not in path or "YearList.do" not in path:
            raise ValueError("학사일정은 경동대학교 ScheduleMgr/YearList.do URL을 입력하세요.")
    else:
        raise ValueError("지원하지 않는 크롤링 소스 유형입니다.")
    return parsed._replace(fragment="").geturl()


def _source_id_seed(label: str, url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    candidates = [label, *(query.get("mCode") or []), parsed.path.rsplit("/", 1)[-1], parsed.netloc]
    for candidate in candidates:
        slug = re.sub(r"[^0-9A-Za-z]+", "_", _as_text(candidate)).strip("_").lower()
        if slug:
            return slug if not slug[0].isdigit() else f"source_{slug}"
    return "source"


def _unique_source_id(config: dict[str, Any], label: str, url: str) -> str:
    existing = {
        _as_text(source.get("id"))
        for group in CRAWL_SOURCE_GROUPS
        for source in config.get(group, [])
    }
    seed = _source_id_seed(label, url)
    candidate = seed
    suffix = 2
    while candidate in existing:
        candidate = f"{seed}_{suffix}"
        suffix += 1
    return candidate


def add_crawl_source(config: dict[str, Any], group: str, *, label: str, category: str, url: str) -> dict[str, Any]:
    """Return a config with one validated source appended."""
    if group not in CRAWL_SOURCE_GROUPS:
        raise ValueError("지원하지 않는 크롤링 소스 유형입니다.")
    updated = load_crawl_config_from_dict(config)
    normalized_url = _validate_crawl_source_url(url, group)
    for existing_group in CRAWL_SOURCE_GROUPS:
        for source in updated.get(existing_group, []):
            if _canonical_source_url(source.get("url")) == _canonical_source_url(normalized_url):
                raise ValueError("이미 등록된 URL입니다.")
    fallback_label = "학사일정" if group == "schedules" else "사용자 공지"
    fallback_category = "학사일정" if group == "schedules" else "사용자추가"
    source_label = _as_text(label) or fallback_label
    entry = {
        "id": _unique_source_id(updated, source_label, normalized_url),
        "label": source_label,
        "category": _as_text(category) or fallback_category,
        "url": normalized_url,
    }
    updated[group].append(entry)
    return updated


def delete_crawl_source(config: dict[str, Any], group: str, source_id: str) -> dict[str, Any]:
    """Return a config with one source removed by group/id."""
    if group not in CRAWL_SOURCE_GROUPS:
        raise ValueError("지원하지 않는 크롤링 소스 유형입니다.")
    updated = load_crawl_config_from_dict(config)
    before = len(updated[group])
    updated[group] = [source for source in updated[group] if _as_text(source.get("id")) != _as_text(source_id)]
    if len(updated[group]) == before:
        raise ValueError("삭제할 URL을 찾지 못했습니다.")
    return updated


def load_crawl_config_from_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize an already-loaded crawler config dictionary."""
    boards = [
        _normal_source_item(item, fallback_id=f"board_{index}", fallback_label=f"공지 게시판 {index}", fallback_category="경동알림")
        for index, item in enumerate(raw.get("boards", []) or [], start=1)
    ]
    schedules = [
        _normal_source_item(item, fallback_id=f"schedule_{index}", fallback_label=f"학사일정 {index}", fallback_category="학사일정")
        for index, item in enumerate(raw.get("schedules", []) or [], start=1)
    ]
    return {
        "boards": boards,
        "schedules": schedules,
        "crawler": {**DEFAULT_CRAWLER_OPTIONS, **(raw.get("crawler", {}) or {})},
    }


def configured_max_pages(default: int = 3) -> int:
    """Read the configured board-page crawl limit for the refresh UI."""
    try:
        config = load_crawl_config()
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
    gemini_thinking_budget: int | None = None,
    gemini_thinking_level: str | None = None,
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
                gemini_thinking_budget=gemini_thinking_budget,
                gemini_thinking_level=gemini_thinking_level,
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


def render_compact_chrome(st: Any) -> None:
    """Hide Streamlit's dev toolbar and leave app-owned settings behind ⋯."""
    st.markdown(
        """
        <style>
          #MainMenu { visibility: hidden; }
          [data-testid="stToolbar"],
          [data-testid="stDecoration"],
          [data-testid="stStatusWidget"],
          [data-testid="stSidebar"],
          [data-testid="stSidebarNav"] {
            display: none !important;
            visibility: hidden !important;
          }
          .block-container { padding-top: 1.35rem; }
          button[kind="primary"],
          [data-testid="stBaseButton-primary"] {
            border: 0 !important;
            border-radius: 999px !important;
            background: linear-gradient(135deg, #2563eb 0%, #0891b2 100%) !important;
            color: #ffffff !important;
            font-weight: 800 !important;
            letter-spacing: -0.01em !important;
            box-shadow: 0 0.55rem 1.2rem rgba(37, 99, 235, 0.24) !important;
            transition: transform 150ms ease, box-shadow 150ms ease, filter 150ms ease !important;
          }
          button[kind="primary"]:hover,
          [data-testid="stBaseButton-primary"]:hover {
            filter: brightness(1.04) saturate(1.08) !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 0.75rem 1.5rem rgba(8, 145, 178, 0.30) !important;
          }
          button[kind="primary"]:focus:not(:active),
          [data-testid="stBaseButton-primary"]:focus:not(:active) {
            outline: 3px solid rgba(37, 99, 235, 0.24) !important;
            outline-offset: 2px !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _session_default(st: Any, key: str, value: Any) -> Any:
    if key not in st.session_state:
        st.session_state[key] = value
    return st.session_state[key]


def render_app() -> None:
    import streamlit as st

    st.set_page_config(page_title="학교 공지 RAG 챗봇", page_icon="🎓", layout="wide", initial_sidebar_state="collapsed")
    render_compact_chrome(st)

    rows = load_notices()
    summary = dataset_summary(rows)

    try:
        from src.gemini_client import (
            gemini_profile_for_model,
            get_gemini_model_profiles,
            list_gemini_models,
            load_gemini_settings,
        )
        from src.ollama_client import list_ollama_models, load_ollama_settings
    except Exception:
        gemini_profile_for_model = get_gemini_model_profiles = list_gemini_models = load_gemini_settings = None  # type: ignore
        list_ollama_models = load_ollama_settings = None  # type: ignore

    ollama_settings = load_ollama_settings() if load_ollama_settings else None
    gemini_settings = load_gemini_settings() if load_gemini_settings else None
    default_provider_label = "추출형만"
    if gemini_settings and gemini_settings.enabled:
        default_provider_label = "Gemini API"
    elif ollama_settings and ollama_settings.enabled:
        default_provider_label = "Ollama"

    _session_default(st, "settings_provider_label", default_provider_label)
    _session_default(st, "settings_crawl_pages", configured_max_pages())
    if ollama_settings:
        _session_default(st, "settings_ollama_base_url", ollama_settings.base_url)
        _session_default(st, "settings_ollama_model", ollama_settings.model)
        _session_default(st, "settings_ollama_num_predict", int(ollama_settings.num_predict))
        _session_default(st, "settings_ollama_timeout", int(ollama_settings.timeout))
    if gemini_settings:
        _session_default(st, "settings_gemini_api_key", "")
        _session_default(st, "settings_gemini_model", gemini_settings.model)
        _session_default(st, "settings_gemini_max_output_tokens", int(gemini_settings.max_output_tokens))
        _session_default(st, "settings_gemini_timeout", int(gemini_settings.timeout))
        _session_default(st, "settings_gemini_thinking_mode", "자동(dynamic)")
        _session_default(st, "settings_gemini_thinking_budget", 1024)
        _session_default(st, "settings_gemini_thinking_level", gemini_settings.thinking_level or "medium")

    @st.dialog("설정")
    def render_settings_dialog() -> None:
        st.subheader("데이터셋")
        cols = st.columns(3)
        cols[0].metric("레코드", summary["count"])
        cols[1].metric("CSV", "있음" if summary["csv_exists"] else "없음")
        cols[2].metric("JSONL", "있음" if summary["jsonl_exists"] else "없음")
        if summary["missing_fields"]:
            st.warning("누락 필드: " + ", ".join(summary["missing_fields"]))
        st.number_input(
            "보드별 크롤링 페이지 수",
            min_value=1,
            max_value=10,
            step=1,
            key="settings_crawl_pages",
            help="데이터셋 새로고침 때만 적용됩니다. 채팅 중에는 크롤링하지 않습니다.",
        )

        with st.expander("크롤링 URL 관리", expanded=False):
            st.caption("여기서 추가/삭제한 경동대학교 공개 URL은 `config/boards.yaml`에 저장되고, 다음 데이터셋 새로고침부터 반영됩니다.")
            try:
                crawl_config = load_crawl_config()
            except Exception as exc:
                st.error(f"크롤링 설정을 읽지 못했습니다: {exc}")
                crawl_config = {"boards": [], "schedules": [], "crawler": DEFAULT_CRAWLER_OPTIONS}

            for group, label in CRAWL_SOURCE_GROUPS.items():
                sources = crawl_config.get(group, [])
                st.markdown(f"**{label} URL {len(sources)}개**")
                if not sources:
                    st.caption("등록된 URL이 없습니다.")
                for source in sources:
                    row = st.columns([0.2, 0.55, 0.15, 0.1])
                    row[0].write(source["label"])
                    row[1].caption(source["url"])
                    row[2].caption(source["category"])
                    if row[3].button("삭제", key=f"delete_source_{group}_{source['id']}"):
                        try:
                            updated_config = delete_crawl_source(load_crawl_config(), group, source["id"])
                            save_crawl_config(updated_config)
                        except Exception as exc:
                            st.error(f"삭제 실패: {exc}")
                        else:
                            st.success(f"삭제됨: {source['label']}")
                            st.rerun()

            st.markdown("**새 URL 추가**")
            st.caption("허용 형식: 공지 게시판은 `www.kduniv.ac.kr/.../Board.do?mCode=...` 목록 URL, 학사일정은 `.../ScheduleMgr/YearList.do?mCode=...` URL입니다.")
            form_version = _session_default(st, "settings_source_form_version", 0)
            kind_key = f"settings_new_source_kind_{form_version}"
            label_key = f"settings_new_source_label_{form_version}"
            category_key = f"settings_new_source_category_{form_version}"
            url_key = f"settings_new_source_url_{form_version}"
            with st.form("settings_add_crawl_source"):
                st.selectbox("유형", options=["공지 게시판", "학사일정"], key=kind_key)
                st.text_input("표시 이름", placeholder="예: 국제공지, 학사일정", key=label_key)
                st.text_input("분류", placeholder="예: 경동알림, 학사일정", key=category_key)
                st.text_input("크롤링 URL", placeholder="https://...", key=url_key)
                submitted = st.form_submit_button("URL 추가")
            if submitted:
                group = "schedules" if st.session_state[kind_key] == "학사일정" else "boards"
                try:
                    updated_config = add_crawl_source(
                        load_crawl_config(),
                        group,
                        label=st.session_state[label_key],
                        category=st.session_state[category_key],
                        url=st.session_state[url_key],
                    )
                    save_crawl_config(updated_config)
                except Exception as exc:
                    st.error(f"추가 실패: {exc}")
                else:
                    st.session_state["settings_source_form_version"] = int(st.session_state["settings_source_form_version"]) + 1
                    st.success("URL을 저장했습니다. 데이터셋 새로고침을 누르면 CSV/JSONL DB가 새 URL 기준으로 재생성됩니다.")
                    st.rerun()

        if st.button("데이터셋 새로고침", key="settings_refresh_dataset"):
            with st.spinner("공지 데이터셋을 갱신하는 중..."):
                ok, output = run_dataset_refresh(max_pages=int(st.session_state["settings_crawl_pages"]))
            (st.success if ok else st.error)("데이터셋 빌드 완료" if ok else "데이터셋 빌드 실패")
            st.code(output[-4000:] if output else "no output")
            st.rerun()

        st.divider()
        st.subheader("AI 답변 생성")
        st.selectbox(
            "답변 생성 방식",
            options=["추출형만", "Ollama", "Gemini API"],
            key="settings_provider_label",
            help="LLM은 검색된 공지/학사일정 근거만 받아 문장화합니다. 실패하면 추출형 답변으로 자동 전환됩니다.",
        )
        provider_label = st.session_state["settings_provider_label"]

        if provider_label == "Ollama":
            if not ollama_settings or not list_ollama_models:
                st.warning("Ollama 설정을 읽지 못했습니다.")
            else:
                st.text_input("Ollama URL", key="settings_ollama_base_url")
                installed_models = list_ollama_models(st.session_state["settings_ollama_base_url"])
                if installed_models:
                    options = installed_models if st.session_state["settings_ollama_model"] in installed_models else [st.session_state["settings_ollama_model"], *installed_models]
                    choice = st.selectbox("설치된 Ollama 모델", options=options, index=options.index(st.session_state["settings_ollama_model"]))
                    st.session_state["settings_ollama_model"] = choice
                else:
                    st.caption("Ollama 모델 목록을 읽지 못했습니다. 모델명을 직접 입력하세요.")
                st.text_input("Ollama 모델명 직접 수정", key="settings_ollama_model")
                with st.expander("Ollama 고급 설정"):
                    st.number_input("Ollama 최대 생성 토큰", min_value=64, max_value=2048, step=64, key="settings_ollama_num_predict")
                    st.number_input("Ollama 응답 제한 시간(초)", min_value=5, max_value=300, step=5, key="settings_ollama_timeout")
                st.caption(f"현재 사용 모델: `{st.session_state['settings_ollama_model']}`")

        elif provider_label == "Gemini API":
            if not gemini_settings or not get_gemini_model_profiles or not gemini_profile_for_model or not list_gemini_models:
                st.warning("Gemini 설정을 읽지 못했습니다.")
            else:
                st.text_input(
                    "Gemini API 키",
                    type="password",
                    placeholder="비워두면 GEMINI_API_KEY / GOOGLE_API_KEY 환경변수 사용",
                    key="settings_gemini_api_key",
                    help="입력한 키는 현재 실행 중인 요청에만 전달하고 파일에 저장하지 않습니다.",
                )
                all_profiles = list(get_gemini_model_profiles())
                api_key = st.session_state["settings_gemini_api_key"] or gemini_settings.api_key
                available_models = list_gemini_models(api_key)
                if available_models:
                    profiles = [profile for profile in all_profiles if profile.code in available_models] or all_profiles
                    st.caption(f"API 키 기준 사용 가능 generateContent 모델 {len(available_models)}개를 확인했습니다.")
                else:
                    profiles = all_profiles
                    st.caption("API 키가 없거나 모델 조회가 실패해 공식 문서 기준 추천 모델 목록을 표시합니다.")

                profile_map = {profile.code: profile for profile in profiles}
                if st.session_state["settings_gemini_model"] not in profile_map:
                    st.session_state["settings_gemini_model"] = profiles[0].code
                st.selectbox(
                    "Gemini 모델",
                    options=[profile.code for profile in profiles],
                    format_func=lambda code: profile_map[code].label,
                    key="settings_gemini_model",
                    help="무료 플랜에서 계정별 접근 가능 모델은 API 키로 조회되며, 없으면 공식 문서 기준 추천 목록을 표시합니다.",
                )
                selected_profile = gemini_profile_for_model(st.session_state["settings_gemini_model"])
                if st.session_state["settings_gemini_max_output_tokens"] > selected_profile.output_token_limit:
                    st.session_state["settings_gemini_max_output_tokens"] = selected_profile.output_token_limit
                with st.expander("Gemini 고급 설정"):
                    st.number_input(
                        "Gemini 최대 생성 토큰",
                        min_value=64,
                        max_value=int(selected_profile.output_token_limit),
                        step=256,
                        key="settings_gemini_max_output_tokens",
                        help=f"{selected_profile.code} 출력 토큰 상한: {selected_profile.output_token_limit:,}",
                    )
                    st.caption(selected_profile.notes)
                    if selected_profile.thinking_control == "budget":
                        thinking_options = ["자동(dynamic)", "직접 설정"]
                        if selected_profile.can_disable_thinking:
                            thinking_options.insert(1, "끄기(0)")
                        if st.session_state["settings_gemini_thinking_mode"] not in thinking_options:
                            st.session_state["settings_gemini_thinking_mode"] = "자동(dynamic)"
                        st.selectbox("Gemini 사고 예산", options=thinking_options, key="settings_gemini_thinking_mode")
                        if st.session_state["settings_gemini_thinking_mode"] == "직접 설정":
                            current_budget = int(st.session_state["settings_gemini_thinking_budget"])
                            st.session_state["settings_gemini_thinking_budget"] = min(
                                max(current_budget, selected_profile.thinking_budget_min),
                                selected_profile.thinking_budget_max,
                            )
                            st.number_input(
                                "thinkingBudget 토큰",
                                min_value=int(selected_profile.thinking_budget_min),
                                max_value=int(selected_profile.thinking_budget_max),
                                step=512,
                                key="settings_gemini_thinking_budget",
                            )
                    elif selected_profile.thinking_control == "level":
                        if st.session_state["settings_gemini_thinking_level"] not in selected_profile.thinking_level_options:
                            st.session_state["settings_gemini_thinking_level"] = selected_profile.default_thinking_level
                        st.selectbox(
                            "Gemini 사고 수준",
                            options=list(selected_profile.thinking_level_options),
                            key="settings_gemini_thinking_level",
                            help="Gemini 3 계열은 thinkingBudget 대신 thinkingLevel을 사용합니다.",
                        )
                    else:
                        st.caption("이 모델은 별도 thinking 설정을 보내지 않습니다.")
                    st.number_input("Gemini 응답 제한 시간(초)", min_value=5, max_value=300, step=5, key="settings_gemini_timeout")
                key_state = "입력 키 사용" if st.session_state["settings_gemini_api_key"] else ("환경변수 키 사용" if gemini_settings.api_key else "키 없음")
                st.caption(f"현재 사용 모델: `{st.session_state['settings_gemini_model']}` · API 키: {key_state}")
        else:
            st.caption("LLM 없이 검색된 근거를 추출형으로 답변합니다.")

    menu_cols = st.columns([0.86, 0.14])
    with menu_cols[0]:
        st.title("🎓 학교 공지 게시판 RAG AI 챗봇")
        st.caption(
            f"수집된 공지/학사일정 {summary['count']}건만 근거로 답변하고, 링크는 아래 출처 카드에서 보여줍니다."
        )
    with menu_cols[1]:
        st.markdown("<div style='height: 0.45rem;'></div>", unsafe_allow_html=True)
        if st.button("⚙️ 설정", key="open_settings", help="설정 열기", type="primary", use_container_width=True):
            render_settings_dialog()

    provider_label = st.session_state.get("settings_provider_label", default_provider_label)
    use_llm = provider_label != "추출형만"
    llm_provider = {"Ollama": "ollama", "Gemini API": "gemini"}.get(provider_label)
    ollama_model = st.session_state.get("settings_ollama_model")
    ollama_base_url = st.session_state.get("settings_ollama_base_url")
    ollama_timeout = st.session_state.get("settings_ollama_timeout")
    ollama_num_predict = st.session_state.get("settings_ollama_num_predict")
    gemini_model = st.session_state.get("settings_gemini_model")
    gemini_api_key = st.session_state.get("settings_gemini_api_key")
    gemini_timeout = st.session_state.get("settings_gemini_timeout")
    gemini_max_output_tokens = st.session_state.get("settings_gemini_max_output_tokens")
    gemini_thinking_budget = None
    gemini_thinking_level = None
    if provider_label == "Gemini API" and gemini_profile_for_model and gemini_model:
        profile = gemini_profile_for_model(gemini_model)
        if profile.thinking_control == "budget":
            mode = st.session_state.get("settings_gemini_thinking_mode", "자동(dynamic)")
            if mode == "끄기(0)":
                gemini_thinking_budget = 0
            elif mode == "직접 설정":
                gemini_thinking_budget = st.session_state.get("settings_gemini_thinking_budget")
            else:
                gemini_thinking_budget = -1
        elif profile.thinking_control == "level":
            gemini_thinking_level = st.session_state.get("settings_gemini_thinking_level", profile.default_thinking_level)

    if not rows:
        st.info("아직 수집된 공지 데이터가 없습니다. 우측 상단 `⋯` 설정창의 데이터셋 새로고침을 실행하거나 `python scripts/build_dataset.py`를 먼저 실행하세요.")

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
                        gemini_thinking_budget=gemini_thinking_budget,
                        gemini_thinking_level=gemini_thinking_level,
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
