#!/usr/bin/env python3
"""Explicit dataset refresh entrypoint for the school notice RAG demo."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.crawler import crawl_from_config
from src.dataset import write_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local KD notice dataset from approved public board URLs.")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "boards.yaml")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--max-pages", type=int, default=None, help="Override configured pages per board for a bounded manual refresh.")
    args = parser.parse_args()

    records = crawl_from_config(args.config, args.data_dir, max_pages_override=args.max_pages)
    written = write_outputs(records, args.data_dir / "notices.csv", args.data_dir / "notices.jsonl")
    print(f"Built dataset: {len(written)} records")
    print(f"CSV: {args.data_dir / 'notices.csv'}")
    print(f"JSONL: {args.data_dir / 'notices.jsonl'}")
    print(f"Crawl log: {args.data_dir / 'crawl_log.jsonl'}")
    if len(written) < 30:
        print("WARNING: fewer than 30 rows collected; inspect crawl_log.jsonl for source/selector limitations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
