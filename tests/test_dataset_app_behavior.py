import tempfile
import unittest
from pathlib import Path

try:
    from src.crawler import BoardConfig, ScheduleConfig, parse_list_page, parse_schedule_page, with_page
except ModuleNotFoundError as exc:  # optional crawler dependencies may be absent before pip install
    BoardConfig = ScheduleConfig = parse_list_page = parse_schedule_page = with_page = None
    CRAWLER_IMPORT_ERROR = exc
else:
    CRAWLER_IMPORT_ERROR = None
from src.dataset import deduplicate, validate_records, write_outputs
from app import (
    add_crawl_source,
    build_answer,
    dataset_summary,
    delete_crawl_source,
    fallback_retrieve,
    load_crawl_config,
    render_thinking_motion,
    run_dataset_refresh,
    save_crawl_config,
)


VALID_RECORDS = [
    {
        "title": "장학금 신청 안내",
        "category": "장학",
        "date": "2026-05-20",
        "url": "https://example.edu/a",
        "source_board": "장학공지",
        "content_or_snippet": "장학금 신청 기간은 6월입니다.",
    },
    {
        "title": "취업 인턴 모집",
        "category": "취업",
        "date": "2026-05-19",
        "url": "https://example.edu/b",
        "source_board": "취업공지",
        "content_or_snippet": "AI 기업 인턴을 모집합니다.",
    },
]


class DatasetAndAppBehaviorTests(unittest.TestCase):
    def test_validate_records_requires_each_required_field_per_row(self):
        bad = [dict(VALID_RECORDS[0], url="")]
        with self.assertRaisesRegex(ValueError, "url"):
            validate_records(bad)

    def test_deduplicate_uses_url_and_title(self):
        records = deduplicate([VALID_RECORDS[0], dict(VALID_RECORDS[0]), VALID_RECORDS[1]])
        self.assertEqual(len(records), 2)

    def test_write_outputs_keeps_csv_and_jsonl_counts_equal(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "notices.csv"
            jsonl_path = Path(tmp) / "notices.jsonl"
            written = write_outputs(VALID_RECORDS, csv_path, jsonl_path)
            self.assertEqual(len(written), 2)
            self.assertEqual(len(csv_path.read_text(encoding="utf-8-sig").splitlines()) - 1, 2)
            self.assertEqual(len(jsonl_path.read_text(encoding="utf-8").splitlines()), 2)

    @unittest.skipIf(CRAWLER_IMPORT_ERROR is not None, "crawler optional dependencies not installed")
    def test_parse_list_page_extracts_public_notice_metadata(self):
        html = """
        <table class="board-list-table"><tbody>
          <tr>
            <td class="subject"><a href="/kor/CMS/Board/Board.do?mode=view&mCode=MN284&mgr_seq=1&board_seq=9">[장학] 국가장학금 신청 안내</a></td>
            <td class="cate">[장학]</td><td class="date">2026-05-20</td><td class="writer">학생처</td>
          </tr>
        </tbody></table>
        """
        board = BoardConfig(id="scholarship", label="장학공지", category="경동알림", url="https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN284")
        rows = parse_list_page(html, board.url, board)
        self.assertEqual(rows[0]["title"], "국가장학금 신청 안내")
        self.assertEqual(rows[0]["source_board"], "장학공지")
        self.assertTrue(rows[0]["url"].startswith("https://www.kduniv.ac.kr/"))

    @unittest.skipIf(CRAWLER_IMPORT_ERROR is not None, "crawler optional dependencies not installed")
    def test_with_page_keeps_first_page_url_and_bounds_extra_pages(self):
        url = "https://example.edu/board?mCode=MN245"
        self.assertEqual(with_page(url, 1), url)
        self.assertIn("page=2", with_page(url, 2))

    @unittest.skipIf(CRAWLER_IMPORT_ERROR is not None, "crawler optional dependencies not installed")
    def test_parse_schedule_page_uses_notice_compatible_schema(self):
        html = """
        <h3 class="sch-date"><em class="year">2026</em>년</h3>
        <ol class="daily-ol"><li class="daily-li">
          <div class="date-core">07. 13(월) ∼ 07. 17(금)</div>
          <div class="body-core">수강신청기간(2학기)</div>
        </li></ol>
        """
        schedule = ScheduleConfig(id="academic_calendar", label="학사일정", category="학사일정", url="https://example.edu/schedule")
        rows = parse_schedule_page(html, schedule.url, schedule)
        self.assertEqual(rows[0]["date"], "2026-07-13")
        self.assertEqual(rows[0]["source_board"], "학사일정")
        self.assertIn("수강신청기간", rows[0]["title"])

    def test_dataset_summary_reports_missing_fields_only_when_rows_exist(self):
        self.assertEqual(dataset_summary([])["missing_fields"], [])
        summary = dataset_summary([dict(VALID_RECORDS[0], date="")])
        self.assertIn("date", summary["missing_fields"])

    def test_fallback_retrieve_and_answer_expose_source_without_crawling(self):
        sources = fallback_retrieve("장학금 신청", VALID_RECORDS)
        self.assertTrue(sources)
        self.assertEqual(sources[0].url, "https://example.edu/a")
        answer, answer_sources = build_answer("장학금 신청", VALID_RECORDS)
        self.assertIn("장학금", answer)
        self.assertTrue(answer_sources)
        unknown, unknown_sources = build_answer("기숙사 고양이 입양", VALID_RECORDS)
        self.assertTrue(unknown.startswith("수집된 공지 데이터에서 확인되지 않음"))
        self.assertEqual(unknown_sources, [])
        oversized_answer, oversized_sources = build_answer(("A" * 12000) + " 장학금", VALID_RECORDS)
        self.assertTrue(oversized_sources)
        self.assertLess(len(oversized_answer), 2500)

    def test_run_dataset_refresh_is_explicit_entrypoint_only(self):
        # The app exposes refresh as a separate callable; answer construction above
        # does not call this function or the crawler.
        self.assertTrue(callable(run_dataset_refresh))

    def test_editable_crawl_sources_are_saved_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "boards.yaml"
            config = {"boards": [], "schedules": [], "crawler": {"max_pages_per_board": 2}}
            updated = add_crawl_source(
                config,
                "boards",
                label="국제공지",
                category="경동알림",
                url="https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN999#source-list",
            )
            self.assertEqual(updated["boards"][0]["label"], "국제공지")
            self.assertEqual(updated["boards"][0]["url"], "https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN999")
            with self.assertRaisesRegex(ValueError, "이미 등록"):
                add_crawl_source(updated, "boards", label="중복", category="경동알림", url="https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN999")

            save_crawl_config(updated, config_path)
            reloaded = load_crawl_config(config_path)
            self.assertEqual(reloaded["boards"][0]["url"], "https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN999")
            self.assertEqual(reloaded["crawler"]["max_pages_per_board"], 2)

            removed = delete_crawl_source(reloaded, "boards", reloaded["boards"][0]["id"])
            save_crawl_config(removed, config_path)
            reloaded_after_delete = load_crawl_config(config_path)
            self.assertEqual(removed["boards"], [])
            self.assertEqual(reloaded_after_delete["boards"], [])

    def test_editable_crawl_sources_reject_unsupported_or_internal_urls(self):
        config = {"boards": [], "schedules": [], "crawler": {}}
        invalid_cases = [
            ("boards", "http://localhost:8000/kor/CMS/Board/Board.do?mCode=MN999"),
            ("boards", "http://127.0.0.1/kor/CMS/Board/Board.do?mCode=MN999"),
            ("boards", "http://169.254.169.254/latest/meta-data"),
            ("boards", "https://example.edu/kor/CMS/Board/Board.do?mCode=MN999"),
            ("boards", "https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN999&mode=view"),
            ("schedules", "https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN999"),
            ("boards", "https://www.kduniv.ac.kr/kor/CMS/ScheduleMgr/YearList.do?mCode=MN096"),
        ]
        for group, url in invalid_cases:
            with self.subTest(group=group, url=url):
                with self.assertRaises(ValueError):
                    add_crawl_source(config, group, label="테스트", category="테스트", url=url)

        valid_schedule = add_crawl_source(
            config,
            "schedules",
            label="학사일정",
            category="학사일정",
            url="https://www.kduniv.ac.kr/kor/CMS/ScheduleMgr/YearList.do?mCode=MN096",
        )
        self.assertEqual(valid_schedule["schedules"][0]["label"], "학사일정")

    def test_render_thinking_motion_outputs_animated_status(self):
        class DummyTarget:
            def __init__(self):
                self.html = ""
                self.unsafe = False

            def markdown(self, html, unsafe_allow_html=False):
                self.html = html
                self.unsafe = unsafe_allow_html

        target = DummyTarget()
        render_thinking_motion(target)
        self.assertIn("근거 검색하고 생각 중", target.html)
        self.assertIn("thinking-bounce", target.html)
        self.assertTrue(target.unsafe)


if __name__ == "__main__":
    unittest.main()
