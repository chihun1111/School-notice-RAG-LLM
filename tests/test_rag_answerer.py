import unittest
from unittest.mock import patch

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

    def test_tied_recent_results_prefer_newer_date(self):
        records = [
            dict(RECORDS[1], title="취업 채용 공지", date="2026-01-01", url="https://example.edu/old"),
            dict(RECORDS[1], title="취업 채용 공지", date="2026-05-07", url="https://example.edu/new"),
        ]
        results = search_notices(records, "최근 취업 채용 공지", top_k=2)
        self.assertEqual(results[0]["url"], "https://example.edu/new")

    def test_academic_calendar_rows_are_searchable(self):
        records = [
            {
                "title": "기말고사(1학기) (06. 16(화) ∼ 06. 22(월))",
                "category": "학사일정",
                "date": "2026-06-16",
                "url": "https://example.edu/schedule",
                "source_board": "학사일정",
                "content_or_snippet": "2026년 학사일정: 06. 16(화) ∼ 06. 22(월) 기말고사(1학기)",
            },
            RECORDS[0],
        ]
        results = search_notices(records, "기말고사 언제야", top_k=1)
        self.assertEqual(results[0]["source_board"], "학사일정")
        self.assertIn("2026-06-16", results[0]["date"])
        self.assertIn("06. 16", results[0]["snippet"])

    def test_general_job_notice_query_does_not_promote_calendar_only_match(self):
        records = [
            {
                "title": "취업역량 경진대회 (11. 18(수))",
                "category": "학사일정",
                "date": "2026-11-18",
                "url": "https://example.edu/schedule",
                "source_board": "학사일정",
                "content_or_snippet": "2026년 학사일정: 11. 18(수) 취업역량 경진대회",
            },
            dict(RECORDS[1], title="경기북부상공회의소 직원 채용", date="2026-05-07"),
        ]
        results = search_notices(records, "최근 취업 채용 공지", top_k=1)
        self.assertNotEqual(results[0]["source_board"], "학사일정")

    def test_unrelated_query_returns_low_confidence_empty_results(self):
        results = search_notices(RECORDS, "기숙사 고양이 입양", min_score=0.35)
        self.assertEqual(results, [])

    def test_answerer_includes_sources_and_evidence(self):
        results = search_notices(RECORDS, "장학금 신청", top_k=1)
        payload = answer_question("장학금 신청", results)
        self.assertIn("수집된 공지 데이터 기준", payload["answer"])
        self.assertEqual(payload["sources"][0]["date"], "2026-05-20")
        self.assertTrue(payload["evidence_snippets"])
        self.assertIn("**요약**", payload["answer"])
        self.assertNotIn("**참고한 근거**", payload["answer"])
        self.assertNotIn("https://example.edu/scholarship", payload["answer"])

    def test_answerer_accepts_streamlit_argument_aliases(self):
        results = search_notices(RECORDS, "장학금 신청", top_k=1)
        payload = answer_question(question="장학금 신청", sources=results, use_llm=False)
        self.assertIn("수집된 공지 데이터 기준", payload["answer"])
        self.assertEqual(payload["sources"][0]["title"], "2026학년도 1학기 국가장학금 신청 안내")

    def test_ollama_generation_uses_local_non_streaming_api(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "model": "llama3.2",
                    "response": "Ollama가 검색된 장학금 공지 근거만 바탕으로 답변했습니다.",
                    "done": True,
                    "eval_count": 12,
                }

        results = search_notices(RECORDS, "장학금 신청", top_k=1)
        with patch.dict(
            "os.environ",
            {
                "KD_NOTICE_LLM_PROVIDER": "ollama",
                "KD_NOTICE_OLLAMA_MODEL": "llama3.2",
                "KD_NOTICE_OLLAMA_BASE_URL": "http://localhost:11434",
            },
            clear=False,
        ):
            with patch("src.ollama_client.requests.post", return_value=FakeResponse()) as mocked_post:
                payload = answer_question("장학금 신청", results, ollama_model="custom-local:7b")

        self.assertTrue(payload["used_llm"])
        self.assertEqual(payload["llm_provider"], "ollama")
        self.assertEqual(payload["llm_status"], "ollama_generated")
        self.assertIn("Ollama", payload["answer"])
        mocked_post.assert_called_once()
        url, = mocked_post.call_args.args
        request_payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(url, "http://localhost:11434/api/generate")
        self.assertEqual(request_payload["model"], "custom-local:7b")
        self.assertFalse(request_payload["stream"])
        self.assertIn("아래 근거에 없는 내용은 추측하지 마세요", request_payload["prompt"])

    def test_ollama_failure_falls_back_to_extractive_answer(self):
        from requests import RequestException

        results = search_notices(RECORDS, "장학금 신청", top_k=1)
        with patch.dict("os.environ", {"KD_NOTICE_LLM_PROVIDER": "ollama"}, clear=False):
            with patch("src.ollama_client.requests.post", side_effect=RequestException("offline")):
                payload = answer_question("장학금 신청", results)

        self.assertFalse(payload["used_llm"])
        self.assertEqual(payload["llm_status"], "ollama_unavailable_fallback")
        self.assertIn("수집된 공지 데이터 기준", payload["answer"])
        self.assertIn("offline", payload["llm_error"])

    def test_ollama_unknown_with_confident_sources_falls_back_to_extractive_answer(self):
        class FakeUnknownResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "model": "qwen2.5-coder:3b",
                    "response": "수집된 공지 데이터에서 확인되지 않음.",
                    "done": True,
                }

        results = search_notices(RECORDS, "취업 인턴", top_k=1)
        with patch.dict("os.environ", {"KD_NOTICE_LLM_PROVIDER": "ollama"}, clear=False):
            with patch("src.ollama_client.requests.post", return_value=FakeUnknownResponse()):
                payload = answer_question("취업 인턴", results)

        self.assertFalse(payload["used_llm"])
        self.assertEqual(payload["llm_status"], "ollama_unknown_fallback")
        self.assertIn("수집된 공지 데이터 기준", payload["answer"])
        self.assertNotEqual(payload["answer"], "수집된 공지 데이터에서 확인되지 않음.")

    def test_gemini_generation_uses_generate_content_rest_api(self):
        class FakeGeminiResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "Gemini가 검색된 장학금 공지 근거만 바탕으로 답변했습니다. 링크: https://example.edu/scholarship"}
                                ]
                            }
                        }
                    ]
                }

        results = search_notices(RECORDS, "장학금 신청", top_k=1)
        with patch.dict("os.environ", {"GEMINI_API_KEY": "env-key"}, clear=False):
            with patch("src.gemini_client.requests.post", return_value=FakeGeminiResponse()) as mocked_post:
                payload = answer_question(
                    "장학금 신청",
                    results,
                    use_llm=True,
                    llm_provider="gemini",
                    gemini_model="gemini-test",
                    gemini_api_key="ui-key",
                )

        self.assertTrue(payload["used_llm"])
        self.assertEqual(payload["llm_provider"], "gemini")
        self.assertEqual(payload["llm_status"], "gemini_generated")
        self.assertIn("Gemini", payload["answer"])
        self.assertNotIn("https://example.edu/scholarship", payload["answer"])
        self.assertNotIn("링크:", payload["answer"])
        mocked_post.assert_called_once()
        url, = mocked_post.call_args.args
        headers = mocked_post.call_args.kwargs["headers"]
        request_payload = mocked_post.call_args.kwargs["json"]
        self.assertEqual(url, "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent")
        self.assertEqual(headers["x-goog-api-key"], "ui-key")
        self.assertEqual(request_payload["contents"][0]["role"], "user")
        self.assertIn("system_instruction", request_payload)
        self.assertIn("아래 근거에 없는 내용은 추측하지 마세요", request_payload["contents"][0]["parts"][0]["text"])

    def test_gemini_failure_falls_back_to_extractive_answer(self):
        from requests import RequestException

        results = search_notices(RECORDS, "장학금 신청", top_k=1)
        with patch.dict("os.environ", {"GEMINI_API_KEY": "env-key"}, clear=False):
            with patch("src.gemini_client.requests.post", side_effect=RequestException("quota")):
                payload = answer_question("장학금 신청", results, use_llm=True, llm_provider="gemini")

        self.assertFalse(payload["used_llm"])
        self.assertEqual(payload["llm_status"], "gemini_unavailable_fallback")
        self.assertIn("수집된 공지 데이터 기준", payload["answer"])
        self.assertIn("quota", payload["llm_error"])

    def test_answerer_safe_unknown_for_empty_results(self):
        payload = answer_question("없는 질문", [])
        self.assertEqual(payload["answer"], SAFE_UNKNOWN_ANSWER)
        self.assertEqual(payload["sources"], [])
        self.assertEqual(payload["confidence"], "low")

    def test_llm_prompt_contains_only_retrieved_evidence(self):
        results = search_notices(RECORDS, "취업 인턴", top_k=1)
        prompt = build_llm_prompt("취업 인턴", results)
        self.assertIn("아래 근거에 없는 내용은 추측하지 마세요", prompt)
        self.assertIn("필드명은 그대로 출력하지 마세요", prompt)
        self.assertIn("답변 본문에는 URL", prompt)
        self.assertIn("AI 기업 현장실습", prompt)
        self.assertNotIn("국가장학금", prompt)

    def test_oversized_question_is_clipped_in_answer_and_prompt(self):
        oversized = "A" * 12000 + " 장학금"
        results = search_notices(RECORDS, "장학금", top_k=1)
        payload = answer_question(oversized, results)
        self.assertLess(len(payload["answer"]), 2500)
        self.assertIn("…", payload["answer"])
        prompt = build_llm_prompt(oversized, results)
        self.assertLess(len(prompt), 2500)
        self.assertIn("…", prompt)


if __name__ == "__main__":
    unittest.main()
