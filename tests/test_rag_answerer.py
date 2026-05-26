import unittest

from src.answerer import SAFE_UNKNOWN_ANSWER, answer_question, build_llm_prompt
from src.rag import NoticeRetriever, search_notices


RECORDS = [
    {
        "title": "2026학년도 1학기 국가장학금 신청 안내",
        "category": "장학",
        "date": "2026-05-20",
        "url": "https://example.edu/scholarship",
        "source_board": "장학공지",
        "content_or_snippet": "국가장학금 신청 기간은 6월 1일부터 6월 20일까지이며 한국장학재단에서 신청합니다.",
    },
    {
        "title": "하계 현장실습 및 취업 연계 인턴 모집",
        "category": "취업",
        "date": "2026-05-18",
        "url": "https://example.edu/job",
        "source_board": "취업공지",
        "content_or_snippet": "AI 기업 현장실습 인턴을 모집하며 지원서 제출 마감은 5월 31일입니다.",
    },
    {
        "title": "중간고사 성적 확인 및 이의신청 안내",
        "category": "학사",
        "date": "2026-04-10",
        "url": "https://example.edu/grade",
        "source_board": "학사공지",
        "content_or_snippet": "성적 확인 기간과 이의신청 방법을 안내합니다.",
    },
]


class RagAnswererTests(unittest.TestCase):
    def test_korean_hybrid_retrieval_returns_relevant_notice(self):
        results = search_notices(RECORDS, "국가장학금 신청 기간 알려줘", top_k=2)
        self.assertTrue(results)
        self.assertIn("국가장학금", results[0]["title"])
        self.assertEqual(results[0]["url"], "https://example.edu/scholarship")
        self.assertGreaterEqual(results[0]["score"], 0.18)

    def test_category_boost_handles_job_terms(self):
        retriever = NoticeRetriever(RECORDS)
        results = retriever.search("AI 인턴 채용 공지", top_k=1)
        self.assertEqual(results[0]["category"], "취업")
        self.assertIn("인턴", results[0]["snippet"])

    def test_unrelated_query_returns_low_confidence_empty_results(self):
        results = search_notices(RECORDS, "기숙사 고양이 입양", min_score=0.35)
        self.assertEqual(results, [])

    def test_answerer_includes_sources_and_evidence(self):
        results = search_notices(RECORDS, "장학금 신청", top_k=1)
        payload = answer_question("장학금 신청", results)
        self.assertIn("수집된 공지 데이터 기준", payload["answer"])
        self.assertEqual(payload["sources"][0]["date"], "2026-05-20")
        self.assertTrue(payload["evidence_snippets"])
        self.assertIn("https://example.edu/scholarship", payload["answer"])

    def test_answerer_safe_unknown_for_empty_results(self):
        payload = answer_question("없는 질문", [])
        self.assertEqual(payload["answer"], SAFE_UNKNOWN_ANSWER)
        self.assertEqual(payload["sources"], [])
        self.assertEqual(payload["confidence"], "low")

    def test_llm_prompt_contains_only_retrieved_evidence(self):
        results = search_notices(RECORDS, "취업 인턴", top_k=1)
        prompt = build_llm_prompt("취업 인턴", results)
        self.assertIn("아래 근거에 없는 내용은 추측하지 마세요", prompt)
        self.assertIn("AI 기업 현장실습", prompt)
        self.assertNotIn("국가장학금", prompt)


if __name__ == "__main__":
    unittest.main()
