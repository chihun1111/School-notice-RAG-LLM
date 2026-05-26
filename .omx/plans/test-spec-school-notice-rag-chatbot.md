# Test Spec — 학교 공지 게시판 RAG AI 챗봇

## Test Strategy
Prioritize evidence that proves the competition demo works end-to-end: configured URLs, bounded crawl, dataset schema, retrieval relevance, grounded answer rendering, and safe unknown behavior.

## Unit Tests

### Crawler parsing
- Given a saved/list-page HTML fixture, parser extracts title/date/category/link when present.
- Missing detail links do not crash parsing; records include available snippet and crawl log warning.
- Non-public/login redirects are skipped and logged.

### Dataset normalization
- Duplicate URLs/titles are deduplicated.
- Required fields are present.
- CSV and JSONL outputs contain the same record count.

### Retrieval
- Korean char n-gram/keyword retrieval returns relevant records for category terms such as 장학, 학사, 취업, 채용.
- Low-confidence unrelated query returns below-threshold result.

### Answerer
- Relevant retrieval result includes source title/date/snippet in answer payload.
- Empty/low-confidence retrieval returns safe unknown.
- Optional LLM prompt, if used, receives only retrieved snippets as evidence.

## Integration Tests
1. Run `python scripts/build_dataset.py`.
   - Expected: `data/notices.csv`, `data/notices.jsonl`, `data/crawl_log.jsonl` exist.
2. Run dataset validation.
   - Expected: required fields exist in every valid row.
3. Run retrieval smoke script or pytest.
   - Expected: at least 4 of 5 prepared demo questions retrieve relevant records.
4. Run answer smoke test.
   - Expected: answer payload has `answer`, `sources`, and `evidence_snippets`.

## E2E / Manual Tests
1. Start app: `streamlit run app.py`.
2. Confirm dataset status is visible.
3. Click each recommended question.
4. Confirm answer card includes:
   - source title or board name,
   - source URL,
   - date or date-related field,
   - evidence snippet.
5. Ask unrelated question: “기숙사 고양이 입양 공지가 있어?”
   - Expected: safe unknown, no fabricated notice.
6. Confirm chat does not trigger continuous crawling unless explicit refresh is clicked.

## Observability / Evidence
- `data/crawl_log.jsonl` records URL, status, count, errors, and timestamps.
- README includes known limitations and run commands.
- Verification summary should include dataset count, record sample, retrieval examples, and unknown response example.

## Planned Verification Commands
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_dataset.py
python -m pytest
streamlit run app.py
```

If pytest is not used:
```bash
python scripts/validate_dataset.py
python scripts/smoke_retrieval.py
```

## Pass/Fail Gates
- FAIL if crawler touches non-user-provided URLs as primary targets without user approval.
- FAIL if login/private data is required.
- FAIL if answers can omit source/evidence metadata.
- FAIL if unrelated questions produce fabricated notice details.
- PASS when local demo can show crawl/dataset evidence and at least one grounded answer plus one safe unknown answer.
