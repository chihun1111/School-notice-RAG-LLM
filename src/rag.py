"""Korean-friendly local retrieval for KD University notice RAG.

The module is intentionally lightweight: it prefers scikit-learn TF-IDF when
available, but keeps a deterministic pure-Python scorer so tests and demo flows
work even before optional dependencies are installed.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REQUIRED_FIELDS = ("title", "category", "date", "url", "source_board", "content_or_snippet")
KOREAN_CATEGORY_TERMS = {
    "장학": ("장학", "국가장학", "학자금", "등록금", "지원금"),
    "학사": ("학사", "수강", "강의", "시험", "성적", "졸업", "휴학", "복학"),
    "취업": ("취업", "채용", "인턴", "현장실습", "진로", "기업"),
    "채용": ("채용", "모집", "인턴", "취업", "공고"),
    "등록": ("등록", "등록금", "납부", "분납"),
}
ACADEMIC_SCHEDULE_TERMS = (
    "학사일정",
    "일정",
    "언제",
    "기간",
    "수강신청",
    "기말고사",
    "중간고사",
    "계절학기",
    "개강",
    "종강",
    "복학",
    "휴학",
    "등록기간",
    "성적",
    "졸업",
)


def normalize_text(value: Any) -> str:
    """Normalize mixed Korean/English text while preserving readable tokens."""
    text = "" if value is None else str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[\u200b\ufeff]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> list[str]:
    """Return word-like tokens plus Korean char n-grams for robust matching."""
    normalized = normalize_text(text).lower()
    word_tokens = re.findall(r"[0-9a-zA-Z가-힣]+", normalized)
    compact = re.sub(r"\s+", "", normalized)
    hangul_runs = re.findall(r"[가-힣]{2,}", compact)
    ngrams: list[str] = []
    for run in hangul_runs:
        for n in (2, 3):
            if len(run) >= n:
                ngrams.extend(run[i : i + n] for i in range(len(run) - n + 1))
    return word_tokens + ngrams


def record_text(record: Mapping[str, Any]) -> str:
    """Build the retrieval document text for one notice record."""
    return " ".join(
        normalize_text(record.get(field, ""))
        for field in ("title", "category", "date", "source_board", "content_or_snippet")
    )


def _first_sentence_with_terms(text: str, terms: Sequence[str], max_chars: int = 180) -> str:
    clean = normalize_text(text)
    if not clean:
        return ""
    if "학사일정:" in clean:
        return clean[:max_chars]
    sentences = re.split(r"(?<=[.!?。！？])\s+|\n+", clean)
    lowered_terms = [term.lower() for term in terms if term]
    for sentence in sentences:
        sentence_clean = normalize_text(sentence)
        lower = sentence_clean.lower()
        if any(term in lower for term in lowered_terms):
            return sentence_clean[:max_chars]
    return clean[:max_chars]


def _date_sort_value(value: str) -> date:
    match = re.search(r"(20\d{2})[-./년\s]*(\d{1,2})?[-./월\s]*(\d{1,2})?", value or "")
    if not match:
        return date.min
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    try:
        return date(year, month, day)
    except ValueError:
        return date.min


def _is_academic_schedule_query(query: str) -> bool:
    return any(term in query for term in ACADEMIC_SCHEDULE_TERMS)


def _upcoming_date_key(value: str) -> tuple[int, int]:
    parsed = _date_sort_value(value)
    if parsed == date.min:
        return (2, 0)
    today = date.today()
    if parsed >= today:
        return (0, parsed.toordinal())
    return (1, -parsed.toordinal())


def load_records(path: str | Path) -> list[dict[str, str]]:
    """Load notices from JSONL or CSV, preserving only expected string fields."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {file_path}")

    rows: list[Mapping[str, Any]]
    if file_path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    elif file_path.suffix.lower() == ".csv":
        with file_path.open("r", encoding="utf-8-sig", newline="") as fp:
            rows = list(csv.DictReader(fp))
    else:
        raise ValueError("Unsupported dataset format; expected .jsonl or .csv")

    records: list[dict[str, str]] = []
    for row in rows:
        normalized = {field: normalize_text(row.get(field, "")) for field in REQUIRED_FIELDS}
        if any(normalized.values()):
            records.append(normalized)
    return records


@dataclass(frozen=True)
class RetrievedNotice:
    """Structured retrieval result used by the answer layer and UI."""

    title: str
    category: str
    date: str
    url: str
    source_board: str
    snippet: str
    score: float
    rank: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "category": self.category,
            "date": self.date,
            "url": self.url,
            "source_board": self.source_board,
            "snippet": self.snippet,
            "score": round(self.score, 4),
            "rank": self.rank,
        }


class NoticeRetriever:
    """Hybrid retriever for notice records.

    Scoring combines lexical overlap, Korean char n-gram overlap, category/date
    boosts, and an optional TF-IDF cosine score if scikit-learn is installed.
    """

    def __init__(self, records: Iterable[Mapping[str, Any]], min_score: float = 0.18) -> None:
        self.records = [self._normalize_record(record) for record in records]
        self.min_score = min_score
        self._documents = [record_text(record) for record in self.records]
        self._token_sets = [set(tokenize(document)) for document in self._documents]
        self._vectorizer = None
        self._matrix = None
        self._init_tfidf()

    @classmethod
    def from_path(cls, path: str | Path, min_score: float = 0.18) -> "NoticeRetriever":
        return cls(load_records(path), min_score=min_score)

    def _init_tfidf(self) -> None:
        # Keep the competition demo deterministic and fast by default. Some
        # local Python/scikit-learn combinations can spend a long time inside
        # native imports, so TF-IDF is an explicit opt-in optimization rather
        # than a requirement for answering from the local dataset.
        if os.getenv("KD_NOTICE_ENABLE_TFIDF") != "1":
            return
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except Exception:
            return
        if not self._documents:
            return
        self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        self._matrix = self._vectorizer.fit_transform(self._documents)

    @staticmethod
    def _normalize_record(record: Mapping[str, Any]) -> dict[str, str]:
        return {field: normalize_text(record.get(field, "")) for field in REQUIRED_FIELDS}

    def search(self, query: str, top_k: int = 5, min_score: float | None = None) -> list[dict[str, Any]]:
        query_clean = normalize_text(query)
        if not query_clean or not self.records:
            return []
        threshold = self.min_score if min_score is None else min_score
        query_tokens = set(tokenize(query_clean))
        tfidf_scores = self._tfidf_scores(query_clean)

        scored: list[tuple[float, int]] = []
        is_schedule_query = _is_academic_schedule_query(query_clean)
        for idx, record in enumerate(self.records):
            score = self._lexical_score(query_clean, query_tokens, idx)
            if tfidf_scores:
                score = (score * 0.65) + (tfidf_scores[idx] * 0.35)
            score += self._metadata_boost(query_clean, record)
            if record.get("source_board") == "학사일정" and not is_schedule_query:
                score -= 0.16
            if score >= threshold:
                scored.append((score, idx))

        if any(term in query_clean for term in ("최근", "최신")):
            scored.sort(
                key=lambda item: (
                    -_date_sort_value(self.records[item[1]].get("date", "")).toordinal(),
                    -item[0],
                    self.records[item[1]].get("title", ""),
                )
            )
        elif is_schedule_query:
            scored.sort(
                key=lambda item: (
                    -item[0],
                    _upcoming_date_key(self.records[item[1]].get("date", "")),
                    self.records[item[1]].get("title", ""),
                )
            )
        else:
            scored.sort(
                key=lambda item: (
                    -item[0],
                    -_date_sort_value(self.records[item[1]].get("date", "")).toordinal(),
                    self.records[item[1]].get("title", ""),
                )
            )
        results: list[RetrievedNotice] = []
        query_terms = list(query_tokens) + [query_clean]
        for rank, (score, idx) in enumerate(scored[:top_k], start=1):
            record = self.records[idx]
            snippet_source = record.get("content_or_snippet") or record.get("title")
            results.append(
                RetrievedNotice(
                    title=record.get("title", ""),
                    category=record.get("category", ""),
                    date=record.get("date", ""),
                    url=record.get("url", ""),
                    source_board=record.get("source_board", ""),
                    snippet=_first_sentence_with_terms(snippet_source, query_terms),
                    score=score,
                    rank=rank,
                )
            )
        return [result.as_dict() for result in results]

    def _tfidf_scores(self, query: str) -> list[float]:
        if self._vectorizer is None or self._matrix is None:
            return []
        query_vector = self._vectorizer.transform([query])
        raw = (self._matrix @ query_vector.T).toarray().ravel().tolist()
        return [float(value) for value in raw]

    def _lexical_score(self, query: str, query_tokens: set[str], record_idx: int) -> float:
        doc_tokens = self._token_sets[record_idx]
        if not query_tokens or not doc_tokens:
            return 0.0
        overlap = query_tokens & doc_tokens
        containment = 1.0 if query.lower() in self._documents[record_idx].lower() else 0.0
        jaccard = len(overlap) / math.sqrt(max(len(query_tokens), 1) * max(len(doc_tokens), 1))
        return min(1.0, jaccard + (0.22 * containment))

    @staticmethod
    def _metadata_boost(query: str, record: Mapping[str, str]) -> float:
        q = query.lower()
        boost = 0.0
        category_text = f"{record.get('category', '')} {record.get('source_board', '')} {record.get('title', '')}".lower()
        for family, terms in KOREAN_CATEGORY_TERMS.items():
            if family in q or any(term in q for term in terms):
                if family in category_text or any(term in category_text for term in terms):
                    boost += 0.12
        years = re.findall(r"20\d{2}", q)
        if years and any(year in record.get("date", "") for year in years):
            boost += 0.06
        return min(boost, 0.24)


def search_notices(records: Iterable[Mapping[str, Any]], query: str, top_k: int = 5, min_score: float = 0.18) -> list[dict[str, Any]]:
    """Convenience function for scripts and Streamlit callbacks."""
    return NoticeRetriever(records, min_score=min_score).search(query, top_k=top_k)
