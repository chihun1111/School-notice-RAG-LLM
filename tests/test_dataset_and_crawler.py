from pathlib import Path

from src.crawler import BoardConfig, ScheduleConfig, parse_detail_page, parse_list_page, parse_schedule_page
from src.dataset import validate_records


def test_parse_kd_board_list_row():
    html = """
    <table class="board-list-table"><tbody>
      <tr><td class="num">1</td><td class="cate"><span>전체</span></td>
      <td class="subject"><p class="stitle"><a href='?mCode=MN245&mode=view&mgr_seq=325&board_seq=1'><span class="cate">[전체]</span> 테스트 공지</a></p></td>
      <td class="writer">교무처</td><td class="date">2026-05-26</td><td class="cnt">3</td></tr>
    </tbody></table>
    """
    rows = parse_list_page(html, "https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN245", BoardConfig("general", "일반공지", "경동알림", "https://example.test"))
    assert len(rows) == 1
    assert rows[0]["title"] == "테스트 공지"
    assert rows[0]["category"] == "전체"
    assert rows[0]["source_board"] == "일반공지"
    assert rows[0]["url"].startswith("https://www.kduniv.ac.kr/kor/CMS/Board/Board.do")


def test_parse_detail_page_board_contents():
    html = '<div id="boardContents"><script>ignore()</script><p>신청 기간은 2026-05-31까지입니다.</p><div class="allim-box">저작권 안내</div></div>'
    assert parse_detail_page(html) == "신청 기간은 2026-05-31까지입니다."


def test_parse_schedule_page_extracts_academic_calendar_rows():
    html = """
    <h3 class="sch-date"><em class="year">2026</em>년</h3>
    <ol class="daily-ol">
      <li class="daily-li">
        <div class="daily-inwr">
          <div class="date-core">06. 16(화) ∼ 06. 22(월)</div>
          <div class="body-core">기말고사(1학기)</div>
        </div>
      </li>
    </ol>
    """
    schedule = ScheduleConfig("academic_calendar", "학사일정", "학사일정", "https://example.edu/schedule")
    rows = parse_schedule_page(html, schedule.url, schedule)
    assert rows[0]["title"] == "기말고사(1학기) (06. 16(화) ∼ 06. 22(월))"
    assert rows[0]["date"] == "2026-06-16"
    assert rows[0]["source_board"] == "학사일정"
    assert "2026년 학사일정" in rows[0]["content_or_snippet"]


def test_validate_records_requires_schema_fields():
    records = [{
        "title": "공지",
        "category": "전체",
        "date": "2026-05-26",
        "url": "https://example.test/notice/1",
        "source_board": "일반공지",
        "content_or_snippet": "내용",
    }]
    assert validate_records(records)[0].title == "공지"
