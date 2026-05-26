# Consensus Plan Draft — 학교 공지 게시판 RAG AI 챗봇

## Source of Truth
- Requirements spec: `.omx/specs/deep-interview-school-notice-rag-chatbot.md`
- Context snapshot: `.omx/context/school-notice-rag-chatbot-20260526T153708Z.md`
- Interview transcript: `.omx/interviews/school-notice-rag-chatbot-20260526T155342Z.md`
- Workspace status: greenfield implementation; no application source files exist yet.

## Requirements Summary
Build a local, demo-ready RAG chatbot for school notice boards. The app must let the team manually run a crawler/dataset builder against the six user-provided public KD University notice board URLs, generate a local dataset, and answer Korean notice questions with cited sources, dates, and evidence snippets. The first-pass goal is a stable competition demo, not a production service.

## RALPLAN-DR Summary

### Principles
1. **Evidence-first answers:** every generated answer must be grounded in retrieved notice records and show source metadata.
2. **Demo stability over architectural complexity:** prefer predictable local files and deterministic fallback behavior over heavier infrastructure.
3. **Bounded crawling:** only user-provided public URLs may be crawled; no login/private data and no continuous runtime crawling.
4. **Graceful degradation:** if no LLM key or no relevant notice is found, the app still returns a safe extractive/unknown response.
5. **Submission alignment:** implementation must visibly support the competition criteria: 전공연계성, AI활용도, 실무활용성, 창의성, 발표력.

### Decision Drivers
1. **Reliable 10-minute presentation:** the system must run locally and show the full pipeline quickly.
2. **Trustworthy RAG behavior:** source title/link/date/snippet must be visible so judges can verify grounding.
3. **Low setup friction:** dependencies and data storage should be simple enough to reproduce before the submission deadline.

### Viable Options

#### Option A — Streamlit + requests/BeautifulSoup + local hybrid TF-IDF search (favored)
- Pros: fast to build, easy to demo, no external vector DB, robust Korean keyword/char matching, works without LLM API.
- Cons: semantic matching is weaker than embedding models; crawler selectors must be tolerant of site markup changes.

#### Option B — Streamlit + embeddings + FAISS/Chroma
- Pros: stronger semantic retrieval, more “AI/RAG” visible technically, scalable to larger corpora.
- Cons: heavier dependencies, model download/API dependency risk, more failure modes for a short competition demo.

#### Option C — crawler + pure keyword search + templated answer only
- Pros: simplest and most deterministic; no hallucination risk.
- Cons: weaker AI활용도 story and less compelling as a RAG chatbot.

### Favored Decision
Use **Option A** as the MVP baseline, while keeping an optional LLM answerer layer behind a safe fallback. This maximizes demo reliability and still demonstrates RAG through retrieval, grounding, and answer synthesis.

## ADR

### Decision
Implement a Streamlit-based local RAG chatbot with a manually triggered crawler/dataset builder, local JSONL/CSV notice dataset, hybrid Korean retrieval, cited answer rendering, and optional LLM answer generation with extractive fallback.

### Drivers
- Competition demo must be stable and quick to run.
- Public notice URLs are known and bounded.
- The system must visibly show source-grounded answers.
- No login/private notice collection is allowed.

### Alternatives Considered
- FAISS/Chroma embedding-first RAG: deferred because dependency/API/model setup risk is higher than the value for the first MVP.
- Pure keyword chatbot: rejected as too weak for AI활용도 and “RAG chatbot” positioning.
- Fully real-time crawler in the app request path: rejected because runtime crawling increases latency and failure risk and conflicts with the clarified non-goal.

### Why Chosen
The chosen approach proves the complete pipeline — crawl → dataset → retrieve → grounded answer — while keeping runtime behavior reproducible for the presentation.

### Consequences
- Search quality may be less semantic than embedding-first RAG, so retrieval tests and curated demo questions are important.
- The crawler must save logs and partial records because site markup can change.
- LLM usage becomes optional rather than mandatory; the AI활용도 story should emphasize RAG design, retrieval grounding, prompt constraints, and optional answer synthesis.

### Follow-ups
- After MVP: add embedding reranker or vector DB if time remains.
- Add PDF/report export only after core RAG flow is verified.
- Consider deployment only after local demo is stable.

## Acceptance Criteria
1. `config/boards.yaml` contains exactly the six user-provided public KD University board URLs unless the user later changes them.
2. `python scripts/build_dataset.py` or equivalent generates `data/notices.csv`, `data/notices.jsonl`, and `data/crawl_log.jsonl`.
3. Dataset generation records at least 30 notice rows when source pages expose sufficient list/detail data; if fewer are available, the crawl log explains why.
4. Every notice row includes `title`, `category`, `date`, `url`, `source_board`, and `content_or_snippet`.
5. `streamlit run app.py` launches a local chat UI without requiring login.
6. UI includes recommended/demo question buttons.
7. A relevant notice question returns an answer plus at least one source title/link/date/snippet.
8. If retrieval confidence is below threshold, the app returns a safe “수집된 공지 데이터에서 확인되지 않음” style answer.
9. App runtime does not continuously crawl; dataset refresh happens only through an explicit user action or CLI command.
10. `README.md` documents setup, dataset build, app run, known limitations, and demo script.
11. Submission docs are updated to describe the RAG chatbot instead of the earlier portfolio analyzer idea.

## Implementation Steps

### 1. Project scaffold and configuration
- Create `requirements.txt` with minimal runtime dependencies: `streamlit`, `requests`, `beautifulsoup4`, `pandas`, `scikit-learn`, `pyyaml`, optionally `python-dotenv`.
- Create `config/boards.yaml` containing the six user-provided URLs and display labels.
- Create source package under `src/` with clear module boundaries.
- Planned files: `requirements.txt`, `config/boards.yaml`, `src/__init__.py`.

### 2. Crawler and dataset builder
- Implement `src/crawler.py` to fetch list pages, identify notice rows/links/dates/categories, and tolerate missing fields.
- Implement detail-page extraction when links are discoverable; otherwise store reliable list-page snippets.
- Implement `src/dataset.py` for normalization, deduplication, CSV/JSONL writing, and crawl log writing.
- Implement `scripts/build_dataset.py` as the explicit non-runtime dataset refresh entrypoint.
- Planned files: `src/crawler.py`, `src/dataset.py`, `scripts/build_dataset.py`, `data/crawl_log.jsonl`.

### 3. Retrieval/RAG core
- Implement `src/rag.py` with Korean-friendly hybrid retrieval: char n-gram TF-IDF plus keyword/date/category boosts.
- Add a confidence threshold for safe unknown answers.
- Return retrieved records with title, URL, date, category, and snippet.
- Planned file: `src/rag.py`.

### 4. Answer generation layer
- Implement `src/answerer.py` that builds grounded answers from retrieved snippets.
- If an LLM API key is available, use a strict prompt that forbids unsupported claims; otherwise use extractive answer templates.
- Ensure unknown questions never hallucinate.
- Planned file: `src/answerer.py`.

### 5. Streamlit demo UI
- Implement `app.py` with sections for dataset status, optional dataset refresh, recommended questions, chat input, answer card, and source/evidence cards.
- Avoid account/admin features.
- Planned file: `app.py`.

### 6. Documentation and submission alignment
- Write `README.md` with setup/run/demo instructions.
- Update `AI_Job_Challenge_기획_문서.md` and `AI_Job_Challenge_제출용_내용_채움본.md` if present, or recreate them if deleted, so the project topic is the school notice RAG chatbot.
- Create `docs/ai_usage_log.md` for AI utilization tracking.
- Planned files: `README.md`, `docs/ai_usage_log.md`, project submission docs.

### 7. Verification and demo rehearsal
- Run dataset build and inspect record count/logs.
- Run retrieval tests for at least five demo questions.
- Run the Streamlit app smoke test.
- Capture evidence for report/PPT: dataset count, example question, answer with source, unknown-question response.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| KD board HTML has non-obvious dynamic markup | crawler may miss details | parse list-page text first, log partial failures, design dataset schema to accept snippets |
| Date/deadline extraction is imperfect | answer may miss deadlines | show 작성일 reliably; extract deadline best-effort from snippets and label uncertain values |
| LLM API unavailable | AI answer generation may fail | implement extractive fallback as required behavior |
| Retrieval misses Korean paraphrases | demo answers weak | use curated recommended questions and char n-gram retrieval with keyword boosts |
| Too few records from source pages | acceptance record count at risk | log actual count; only add clearly labeled sample fixtures after user approval |
| Hallucinated answers | credibility loss | confidence threshold + safe unknown + displayed evidence snippets |

## Verification Steps
1. `python scripts/build_dataset.py --config config/boards.yaml --out data/notices.jsonl` completes with nonzero records and a crawl log.
2. `python -m pytest` or lightweight script checks dataset schema and retrieval behavior.
3. `streamlit run app.py` launches and renders recommended questions.
4. Manual smoke questions:
   - “장학 관련 공지 알려줘”
   - “취업 공지 중 최근 항목 알려줘”
   - “학사 일정 관련 공지가 있어?”
   - “채용 공지 알려줘”
   - “기숙사 고양이 입양 공지가 있어?” → safe unknown expected if not in data.
5. Inspect answer cards for source title/link/date/snippet.
6. Verify no crawler loop runs automatically in normal chat requests.

## Available-Agent-Types Roster
Known useful roles from this workspace catalog:
- `explore` — repo/file inspection and current implementation mapping.
- `planner` — sequencing and implementation plan maintenance.
- `architect` — architecture review, tradeoff pressure, interface boundaries.
- `executor` — implementation/refactoring owner.
- `debugger` — crawler/parser/RAG failure diagnosis.
- `test-engineer` — dataset, retrieval, and UI smoke test design.
- `verifier` — completion evidence and acceptance-criteria audit.
- `writer` — README, report, AI utilization log, presentation copy.
- `critic` / `code-reviewer` — final plan/code challenge and risk review.
- `dependency-expert` — only if dependency selection becomes contested.

## Follow-up Staffing Guidance

### Recommended `$ultragoal` default
Use `$ultragoal` as durable owner for sequential delivery. Suggested lane sequence:
1. `executor` medium — scaffold + crawler + dataset builder.
2. `executor` medium — RAG/search + answerer + Streamlit UI.
3. `test-engineer` medium — dataset/retrieval/UI smoke checks.
4. `writer` medium — README/submission docs update.
5. `verifier` high — acceptance evidence and final audit.

### Team + Ultragoal option
Use Team + Ultragoal if parallel execution is desired. Team handles coordinated lanes; Ultragoal owns durable goal/ledger checkpoints.

Suggested Team lanes:
- Worker 1 / `executor`: crawler + dataset files.
- Worker 2 / `executor`: retrieval + answerer.
- Worker 3 / `executor` or `designer`: Streamlit UI.
- Worker 4 / `test-engineer`: verification fixtures and smoke tests.
- Worker 5 / `writer`: README, report, AI usage log.

### Ralph fallback
Use `$ralph` only if explicitly selecting a persistent single-owner sequential verification/fix lane. It is not the default follow-up because `$ultragoal` is better suited for durable goal tracking.

## Goal-Mode Follow-up Suggestions
- `$ultragoal` — recommended default for implementation and completion tracking.
- `$autoresearch-goal` — not recommended here; this is not primarily a research deliverable.
- `$performance-goal` — not recommended initially; no measurable latency/throughput optimization target has been requested.
- `$team` — useful if you want crawler/RAG/UI/docs built in parallel under an Ultragoal checkpoint ledger.

## Launch Hints

### Single-owner durable path
```bash
$ultragoal .omx/plans/consensus-plan-school-notice-rag-chatbot.md
```

### Team path
```bash
$team .omx/plans/consensus-plan-school-notice-rag-chatbot.md
# or from shell/runtime:
omx team --task-file .omx/plans/consensus-plan-school-notice-rag-chatbot.md
```

### Team verification path
Before Team shutdown, Team should prove:
- dataset builder ran and produced records/logs,
- retrieval returns relevant records for demo questions,
- UI renders answer/source/date/evidence cards,
- unknown-question safety works,
- docs reflect the RAG chatbot topic.

Ultragoal should checkpoint those artifacts as durable completion evidence: command outputs, generated dataset summary, screenshots or smoke-test notes, and changed-file list.

## Changelog
- Draft v1 created from deep-interview spec.
