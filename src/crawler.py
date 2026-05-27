"""Bounded public notice-board crawler for the KD University RAG demo."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
import yaml
from bs4 import BeautifulSoup

from .dataset import NoticeRecord, clean_text


@dataclass(frozen=True)
class BoardConfig:
    id: str
    label: str
    category: str
    url: str


@dataclass(frozen=True)
class ScheduleConfig:
    id: str
    label: str
    category: str
    url: str


def load_config(path: Path) -> tuple[list[BoardConfig], list[ScheduleConfig], dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    boards = [BoardConfig(**item) for item in raw.get("boards", [])]
    schedules = [ScheduleConfig(**item) for item in raw.get("schedules", [])]
    crawler = raw.get("crawler", {}) or {}
    return boards, schedules, crawler


class CrawlLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def log(self, event: str, **fields: Any) -> None:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


class NoticeCrawler:
    def __init__(self, *, timeout: float = 12, delay: float = 0.25, user_agent: str | None = None, logger: CrawlLogger | None = None):
        self.timeout = timeout
        self.delay = delay
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or "KDUniversityNoticeRAGDemo/0.1 (+public pages only)",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        })

    def fetch(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        time.sleep(self.delay)
        return response.text

    def crawl_board(self, board: BoardConfig, max_pages: int = 1) -> list[NoticeRecord]:
        records: list[NoticeRecord] = []
        for page in range(1, max_pages + 1):
            page_url = with_page(board.url, page)
            try:
                html = self.fetch(page_url)
                items = parse_list_page(html, page_url, board)
                if self.logger:
                    self.logger.log("list_page", board_id=board.id, board_label=board.label, page=page, url=page_url, status="ok", item_count=len(items))
            except Exception as exc:  # pragma: no cover - network failure path
                if self.logger:
                    self.logger.log("list_page", board_id=board.id, board_label=board.label, page=page, url=page_url, status="error", error=str(exc))
                continue
            for item in items:
                try:
                    detail_html = self.fetch(item["url"])
                    snippet = parse_detail_page(detail_html) or item.get("content_or_snippet") or item["title"]
                    records.append(NoticeRecord(**{**item, "content_or_snippet": snippet}))
                    if self.logger:
                        self.logger.log("detail_page", board_id=board.id, url=item["url"], status="ok", title=item["title"])
                except Exception as exc:  # pragma: no cover - network failure path
                    fallback = NoticeRecord(**{**item, "content_or_snippet": item.get("content_or_snippet") or item["title"]})
                    records.append(fallback)
                    if self.logger:
                        self.logger.log("detail_page", board_id=board.id, url=item["url"], status="partial", title=item["title"], error=str(exc))
        return records

    def crawl_schedule(self, schedule: ScheduleConfig) -> list[NoticeRecord]:
        try:
            html = self.fetch(schedule.url)
            items = parse_schedule_page(html, schedule.url, schedule)
            if self.logger:
                self.logger.log("schedule_page", schedule_id=schedule.id, schedule_label=schedule.label, url=schedule.url, status="ok", item_count=len(items))
        except Exception as exc:  # pragma: no cover - network failure path
            if self.logger:
                self.logger.log("schedule_page", schedule_id=schedule.id, schedule_label=schedule.label, url=schedule.url, status="error", error=str(exc))
            return []
        return [NoticeRecord(**item) for item in items]


def with_page(url: str, page: int) -> str:
    if page <= 1:
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["page"] = [str(page)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def parse_list_page(html: str, page_url: str, board: BoardConfig) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.board-list-table tbody tr")
    records: list[dict[str, str]] = []
    for row in rows:
        link = row.select_one("td.subject a[href]") or row.select_one("a[href*='mode=view']")
        if not link:
            continue
        title = clean_text(link.get_text(" "))
        category = clean_text((row.select_one("td.cate") or row.select_one("span.cate") or {}).get_text(" ") if (row.select_one("td.cate") or row.select_one("span.cate")) else "")
        if category.startswith("[") and category.endswith("]"):
            category = category[1:-1]
        date = clean_text(row.select_one("td.date").get_text(" ") if row.select_one("td.date") else "")
        writer = clean_text(row.select_one("td.writer").get_text(" ") if row.select_one("td.writer") else "")
        url = urljoin(page_url, link.get("href", ""))
        bracketed = re.match(r"^\[([^\]]+)\]\s*(.+)$", title)
        if bracketed:
            category = category or clean_text(bracketed.group(1))
            title = clean_text(bracketed.group(2))
        title = title.replace(f"[{category}]", "", 1).strip() if category else title
        if not title or "mode=view" not in url:
            continue
        records.append({
            "title": title,
            "category": category or board.category,
            "date": date,
            "url": url,
            "source_board": board.label,
            "content_or_snippet": title,
            "writer": writer,
            "board_id": board.id,
        })
    return records


def parse_detail_page(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in ["#boardContents", ".board-view-contents", ".board-view-cont"]:
        node = soup.select_one(selector)
        if not node:
            continue
        for noisy in node.select("script, style, .allim-box"):
            noisy.decompose()
        text = clean_text(node.get_text(" "))
        if text:
            return text[:2000]
    return ""


def _schedule_year(soup: BeautifulSoup) -> int:
    year_node = soup.select_one(".sch-date .year")
    if year_node:
        year_text = clean_text(year_node.get_text(" "))
        if year_text.isdigit():
            return int(year_text)
    match = re.search(r"(20\d{2})\s*년", soup.get_text(" ", strip=True))
    if match:
        return int(match.group(1))
    return datetime.now().year


def _schedule_start_date(year: int, date_text: str) -> str:
    match = re.search(r"(\d{1,2})\.\s*(\d{1,2})", date_text)
    if not match:
        return f"{year}-01-01"
    month = int(match.group(1))
    day = int(match.group(2))
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_schedule_page(html: str, page_url: str, schedule: ScheduleConfig) -> list[dict[str, str]]:
    """Parse KD University yearly academic schedule entries into RAG rows."""
    soup = BeautifulSoup(html, "html.parser")
    year = _schedule_year(soup)
    records: list[dict[str, str]] = []
    for item in soup.select("li.daily-li"):
        date_node = item.select_one(".date-core")
        body_node = item.select_one(".body-core")
        date_text = clean_text(date_node.get_text(" ") if date_node else "")
        body_text = clean_text(body_node.get_text(" ") if body_node else "")
        if not date_text or not body_text:
            continue
        start_date = _schedule_start_date(year, date_text)
        title = f"{body_text} ({date_text})"
        records.append(
            {
                "title": title,
                "category": schedule.category,
                "date": start_date,
                "url": page_url,
                "source_board": schedule.label,
                "content_or_snippet": f"{year}년 학사일정: {date_text} {body_text}",
                "writer": "",
                "board_id": schedule.id,
            }
        )
    return records


def crawl_from_config(config_path: Path, data_dir: Path, *, max_pages_override: int | None = None) -> list[NoticeRecord]:
    boards, schedules, options = load_config(config_path)
    logger = CrawlLogger(data_dir / "crawl_log.jsonl")
    crawler = NoticeCrawler(
        timeout=float(options.get("request_timeout_seconds", 12)),
        delay=float(options.get("polite_delay_seconds", 0.25)),
        user_agent=str(options.get("user_agent", "KDUniversityNoticeRAGDemo/0.1")),
        logger=logger,
    )
    max_pages = int(max_pages_override or options.get("max_pages_per_board", 1))
    all_records: list[NoticeRecord] = []
    logger.log("crawl_start", board_count=len(boards), schedule_count=len(schedules), max_pages_per_board=max_pages)
    for board in boards:
        records = crawler.crawl_board(board, max_pages=max_pages)
        all_records.extend(records)
        logger.log("board_complete", board_id=board.id, board_label=board.label, records=len(records))
    for schedule in schedules:
        records = crawler.crawl_schedule(schedule)
        all_records.extend(records)
        logger.log("schedule_complete", schedule_id=schedule.id, schedule_label=schedule.label, records=len(records))
    logger.log("crawl_complete", total_records=len(all_records))
    return all_records
