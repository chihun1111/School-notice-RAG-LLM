#!/usr/bin/env python3
"""Smoke-test retrieval and answer safety against the local dataset."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.answerer import SAFE_UNKNOWN_ANSWER, answer_question
from src.rag import NoticeRetriever, load_records

DATASET = ROOT / "data" / "notices.jsonl"
QUESTIONS = [
    "장학금 신청 관련 공지를 알려줘",
    "학사 일정이나 수강신청 관련 공지가 있어?",
    "취업 또는 채용 관련 최근 공지를 찾아줘",
    "학생지원 프로그램 공지를 요약해줘",
]
UNKNOWN_QUESTION = "기숙사 고양이 입양 공지가 있어?"


def main() -> int:
    if not DATASET.exists():
        raise SystemExit(f"missing dataset: {DATASET}; run python scripts/build_dataset.py first")
    records = load_records(DATASET)
    retriever = NoticeRetriever(records)
    print(f"Dataset rows: {len(records)}")
    passes = 0
    for question in QUESTIONS:
        results = retriever.search(question, top_k=3)
        payload = answer_question(question, results)
        has_source = bool(payload.get("sources"))
        print(f"QUESTION: {question}")
        print(f"  results={len(results)} has_source={has_source} confidence={payload.get('confidence')}")
        if has_source:
            top = payload["sources"][0]
            print(f"  top={top.get('title')} | {top.get('date')} | {top.get('url')}")
            passes += 1
    unknown_results = retriever.search(UNKNOWN_QUESTION, top_k=3, min_score=0.5)
    unknown_payload = answer_question(UNKNOWN_QUESTION, unknown_results, min_score=0.5)
    print(f"UNKNOWN: {UNKNOWN_QUESTION}")
    print(f"  answer={unknown_payload.get('answer')}")
    if unknown_payload.get("answer") != SAFE_UNKNOWN_ANSWER:
        raise SystemExit("safe unknown check failed")
    if passes == 0:
        raise SystemExit("no demo question returned a sourced answer")
    print(f"Smoke retrieval PASS: {passes}/{len(QUESTIONS)} demo questions returned sources; unknown question was safe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
