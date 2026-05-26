#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dataset import validate_records

path = ROOT / "data" / "notices.csv"
if not path.exists():
    raise SystemExit(f"missing dataset: {path}")
with path.open(encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
validated = validate_records(rows)
print(f"Dataset validation PASS: {len(validated)} rows")
