"""Dataset normalization, validation, and persistence for KD notice records."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

REQUIRED_FIELDS = ["title", "category", "date", "url", "source_board", "content_or_snippet"]


@dataclass(frozen=True)
class NoticeRecord:
    title: str
    category: str
    date: str
    url: str
    source_board: str
    content_or_snippet: str
    writer: str = ""
    board_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_record(record: dict[str, object] | NoticeRecord) -> NoticeRecord:
    data = record.to_dict() if isinstance(record, NoticeRecord) else dict(record)
    title = clean_text(data.get("title"))
    category = clean_text(data.get("category"))
    date = clean_text(data.get("date"))
    url = clean_text(data.get("url"))
    source_board = clean_text(data.get("source_board"))
    snippet = clean_text(data.get("content_or_snippet"))
    if not snippet:
        snippet = title
    return NoticeRecord(
        title=title,
        category=category,
        date=date,
        url=url,
        source_board=source_board,
        content_or_snippet=snippet,
        writer=clean_text(data.get("writer")),
        board_id=clean_text(data.get("board_id")),
    )


def deduplicate(records: Iterable[dict[str, object] | NoticeRecord]) -> list[NoticeRecord]:
    seen: set[tuple[str, str]] = set()
    output: list[NoticeRecord] = []
    for item in records:
        record = normalize_record(item)
        key = (record.url, record.title)
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def validate_records(records: Iterable[dict[str, object] | NoticeRecord]) -> list[NoticeRecord]:
    normalized = deduplicate(records)
    if not normalized:
        raise ValueError("dataset contains no notice rows")
    missing_by_field: dict[str, int] = {field: 0 for field in REQUIRED_FIELDS}
    bad_rows: list[str] = []
    for idx, record in enumerate(normalized, start=1):
        data = record.to_dict()
        missing = [field for field in REQUIRED_FIELDS if not clean_text(data.get(field))]
        for field in missing:
            missing_by_field[field] += 1
        if missing:
            bad_rows.append(f"row {idx}: missing {', '.join(missing)}")
    fields_missing_from_all = [field for field, count in missing_by_field.items() if count == len(normalized)]
    if fields_missing_from_all:
        raise ValueError("required field(s) missing from all rows: " + ", ".join(fields_missing_from_all))
    if bad_rows:
        raise ValueError("invalid notice rows: " + "; ".join(bad_rows[:10]))
    return normalized


def write_outputs(records: Iterable[dict[str, object] | NoticeRecord], csv_path: Path, jsonl_path: Path) -> list[NoticeRecord]:
    validated = validate_records(records)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(NoticeRecord.__dataclass_fields__.keys())
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in validated:
            writer.writerow(record.to_dict())
    with jsonl_path.open("w", encoding="utf-8") as f:
        for record in validated:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return validated
