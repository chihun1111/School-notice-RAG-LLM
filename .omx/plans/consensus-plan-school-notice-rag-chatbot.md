# Final Consensus Plan — 학교 공지 게시판 RAG AI 챗봇

## Source of Truth
- Requirements spec: `.omx/specs/deep-interview-school-notice-rag-chatbot.md`
- Context snapshot: `.omx/context/school-notice-rag-chatbot-20260526T153708Z.md`
- Interview transcript: `.omx/interviews/school-notice-rag-chatbot-20260526T155342Z.md`
- Architect review: `.omx/drafts/architect-review-school-notice-rag-chatbot.md`
- Critic review: `.omx/drafts/critic-review-school-notice-rag-chatbot.md`
- Workspace status: greenfield implementation; no application source files currently exist.

## Requirements Summary
Build a local, demo-ready RAG chatbot for school notice boards. The app must let the team manually run a crawler/dataset builder against the six user-provided public KD University notice board URLs, generate a local dataset, and answer Korean notice questions with cited sources, dates, and evidence snippets. The first-pass goal is a stable competition demo, not a production service.

## RALPLAN-DR Summary

### Principles
1. **Evidence-first answers:** every answer must be grounded in retrieved notice records and show source metadata.
2. **Demo stability over architectural complexity:** prefer predictable local files and deterministic fallback behavior over heavier infrastructure.
3. **Bounded crawling:** only user-provided public URLs may be crawled; no login/private data and no continuous runtime crawling.
4. **Graceful degradation:** if no LLM key or no relevant notice is found, the app still returns a safe extractive/unknown response.
5. **Submission alignment:** implementation must visibly support 전공연계성, AI활용도, 실무활용성, 창의성, 발표력.

### Decision Drivers
1. **Reliable 10-minute presentation:** the system must run locally and show the full crawl → dataset → RAG answer pipeline quickly.
2. **Trustworthy RAG behavior:** source title/link/date/snippet must be visible so judges can verify grounding.
3. **Low setup friction:** dependencies and storage should be simple enough to reproduce before submission.

### Viable Options

#### Option A — Streamlit + requests/BeautifulSoup + local hybrid TF-IDF retrieval (favored)
- Pros: fast to build, easy to demo, no external vector DB, robust Korean keyword/char matching, works without LLM API.
- Cons: semantic matching is weaker than embedding models; crawler selectors must tolerate site markup changes.

#### Option B — Streamlit + embeddings + FAISS/Chroma
- Pros: stronger semantic retrieval, more recognizable “AI/RAG” architecture, scalable to larger corpora.
- Cons: heavier dependencies, model/API setup risk, more failure modes for a short competition demo.

#### Option C — crawler + pure keyword search + templated answer only
- Pros: simplest and most deterministic; no hallucination risk.
- Cons: weaker AI활용도 story and less compelling as an AI chatbot.

#### Option D — app-runtime real-time crawler
- Pros: freshest data.
- Cons: higher latency/failure risk, harder to verify during presentation, conflicts with clarified non-goal of no continuous runtime crawling.

### Favored Decision
Use **Option A** as the MVP baseline, with optional LLM grounded-answer synthesis as a first-class enhancement and extractive fallback as required behavior. This protects demo stability while preserving the AI활용도 story through RAG design, constrained prompt generation, citation display, and AI usage documentation.

## ADR

### Decision
Implement a Streamlit-based local RAG chatbot with a manually triggered crawler/dataset builder, local JSONL/CSV notice dataset, hybrid Korean retrieval, cited answer rendering, and optional LLM answer generation with extractive fallback.

### Drivers
- Competition demo must be stable and quick to run.
- Public notice URLs are known and bounded.
- The system must visibly show source-grounded answers.
- No login/private notice collection is allowed.
- AI활용도 must be demonstrable without making the app dependent on fragile external services.

### Alternatives Considered
- FAISS/Chroma embedding-first RAG: deferred because dependency/API/model setup risk is higher than first-MVP value.
- Pure keyword chatbot: rejected as too weak for AI활용도 and “RAG chatbot” positioning.
- Runtime real-time crawler: rejected because runtime crawling increases latency/failure risk and violates clarified scope.
- Production web service: rejected because actual deployment/monitoring/user accounts are out of scope.

### Why Chosen
The chosen approach proves the complete pipeline — crawl → dataset → retrieve → grounded answer — while keeping runtime behavior reproducible for the presentation. It also leaves room for optional LLM/embedding upgrades if time remains.

### Consequences
- Search quality may be less semantic than embedding-first RAG, so retrieval tests and curated demo questions are important.
- The crawler must save logs and partial records because site markup can change.
- LLM usage is optional rather than mandatory; documentation must clearly explain RAG, prompt constraints, and grounded synthesis.

### Follow-ups
- After MVP: add embedding reranker or vector DB if local demo is stable.
- Add PDF/report export only after core RAG flow is verified.
- Consider deployment only after local demo is stable and user explicitly approves.

## Crawler Safety and Data Ethics Constraints
- Crawl only the six user-provided public URLs unless the user updates the URL list.
- Do not access login-required, private, or permission-gated notices.
- Use bounded page count, request timeout, polite delay, and a descriptive user-agent.
- Save `data/crawl_log.jsonl` with success/failure evidence instead of silently hiding crawl failures.
- Do not mix synthetic/sample notices into the real answer corpus unless they are clearly labeled and the user explicitly approves.
- App chat requests must not trigger continuous crawling; dataset refresh must be explicit.

## Acceptance Criteria
1. `config/boards.yaml` contains the six user-provided public KD University board URLs and display labels.
2. `python scripts/build_dataset.py` generates `data/notices.csv`, `data/notices.jsonl`, and `data/crawl_log.jsonl`.
3. Dataset generation targets 30+ notice rows when source pages expose sufficient data. If fewer are available, `crawl_log.jsonl` must explain source/selector limitations and no fake real notices may be inserted.
4. Every notice row includes `title`, `category`, `date`, `url`, `source_board`, and `content_or_snippet`.
5. Dataset validation checks fail when required fields are missing from all rows.
6. `streamlit run app.py` launches a local chat UI without requiring login.
7. UI includes recommended/demo question buttons.
8. A relevant notice question returns an answer plus at least one source title/link/date/snippet.
9. If retrieval confidence is below threshold, the app returns a safe “수집된 공지 데이터에서 확인되지 않음” style answer.
10. App runtime does not continuously crawl; dataset refresh happens only through explicit button/CLI action.
11. `README.md` documents setup, dataset build, app run, known limitations, demo script, and AI/RAG explanation.
12. Submission docs are updated/recreated to describe the school notice RAG chatbot, not the earlier portfolio analyzer idea.

## Implementation Steps

### 1. Project scaffold and configuration
- Create `requirements.txt` with minimal dependencies: `streamlit`, `requests`, `beautifulsoup4`, `pandas`, `scikit-learn`, `pyyaml`, optionally `python-dotenv`.
- Create `config/boards.yaml` with six user-provided URLs and labels.
- Create source package boundaries.
- Planned files: `requirements.txt`, `config/boards.yaml`, `src/__init__.py`.

### 2. Crawler parser discovery and dataset builder
- Inspect one list page and at least one reachable detail path pattern before finalizing selectors.
- Implement `src/crawler.py` with tolerant list-page extraction and detail-page best effort.
- Preserve title/date/category/source even when detail body extraction fails.
- Implement bounded request count, timeout, polite delay, and crawl logging.
- Implement `src/dataset.py` for normalization, deduplication, schema validation, CSV/JSONL writing.
- Implement `scripts/build_dataset.py` as the explicit dataset refresh entrypoint.
- Planned files: `src/crawler.py`, `src/dataset.py`, `scripts/build_dataset.py`, `data/crawl_log.jsonl`.

### 3. Retrieval/RAG core
- Implement `src/rag.py` with Korean-friendly hybrid retrieval: char n-gram TF-IDF plus keyword/date/category boosts.
- Add confidence threshold for safe unknown answers.
- Return structured retrieved records with title, URL, date, category, snippet, and score.
- Planned file: `src/rag.py`.

### 4. Grounded answer layer
- Implement `src/answerer.py` that builds grounded answers from retrieved snippets.
- If an LLM API key is available, use a strict prompt that permits only retrieved evidence and requires uncertainty handling.
- If no LLM key is available, use extractive answer templates.
- Planned file: `src/answerer.py`.

### 5. Streamlit demo UI
- Implement `app.py` with dataset status, explicit dataset refresh, recommended questions, chat input, answer card, source/date/evidence cards, and unknown-state message.
- Avoid account/admin features.
- Planned file: `app.py`.

### 6. Documentation and submission alignment
- Write `README.md` with setup/run/demo instructions and AI활용도 narrative.
- Create `docs/ai_usage_log.md` for AI utilization tracking.
- Update or recreate `AI_Job_Challenge_기획_문서.md` and `AI_Job_Challenge_제출용_내용_채움본.md` for the RAG chatbot topic.
- Planned files: `README.md`, `docs/ai_usage_log.md`, project submission docs.

### 7. Verification and demo rehearsal
- Run dataset build and schema validation.
- Run retrieval and safe-unknown tests.
- Run Streamlit smoke test.
- Capture evidence for report/PPT: dataset count, crawl log summary, example answer with source/date/snippet, unknown-question response.

## Verification Commands
Planned commands after implementation:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_dataset.py
python -m pytest
streamlit run app.py
```

If `pytest` is not introduced, replace with a checked script such as:

```bash
python scripts/validate_dataset.py
python scripts/smoke_retrieval.py
```

## Definition of Done
- Dataset build completes or fails with actionable crawl logs.
- Required dataset schema is valid.
- At least five demo questions have verified retrieval/answer behavior.
- Unknown-question safety behavior is demonstrated.
- Streamlit UI shows answer, source, date, and evidence snippet.
- README and submission docs are aligned with the RAG chatbot topic.
- No non-goal features were implemented.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| KD board HTML has non-obvious/dynamic markup | crawler may miss details | parser-discovery step, list-page fallback, partial failure logs |
| Date/deadline extraction is imperfect | answer may miss deadlines | show 작성일 reliably; extract deadline best-effort and label uncertainty |
| LLM API unavailable | answer generation may fail | extractive fallback is required behavior |
| Retrieval misses Korean paraphrases | demo answers weak | char n-gram retrieval, keyword boosts, curated recommended questions |
| Too few records from source pages | record-count target at risk | crawl log explains source limits; no fabricated real notices without approval |
| Hallucinated answers | credibility loss | confidence threshold, strict prompt, safe unknown, visible snippets |
| Site load/ethics issue | inappropriate crawling | bounded pages, timeout, delay, public-only URLs |

## Test Spec Link
Detailed test plan: `.omx/plans/test-spec-school-notice-rag-chatbot.md`

## Available-Agent-Types Roster
Known useful roles from this workspace catalog:
- `explore` — repo/file inspection and implementation mapping.
- `planner` — sequencing and plan maintenance.
- `architect` — architecture review and tradeoff pressure.
- `executor` — implementation/refactoring owner.
- `debugger` — crawler/parser/RAG failure diagnosis.
- `test-engineer` — dataset, retrieval, and UI smoke tests.
- `verifier` — acceptance-criteria audit and completion evidence.
- `writer` — README, report, AI utilization log, presentation copy.
- `critic` / `code-reviewer` — final challenge and risk review.
- `dependency-expert` — only if dependency selection becomes contested.

## Follow-up Staffing Guidance

### Recommended `$ultragoal` default
Use `$ultragoal` as durable owner for sequential delivery.
1. `executor` medium — scaffold + crawler + dataset builder.
2. `executor` medium — RAG/search + answerer + Streamlit UI.
3. `test-engineer` medium — dataset/retrieval/UI tests.
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
- `$autoresearch-goal` — not recommended; this is not primarily a research deliverable.
- `$performance-goal` — not recommended initially; no measurable latency/throughput target has been requested.
- `$team` — useful if crawler/RAG/UI/docs should be built in parallel under Ultragoal checkpointing.

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

### Team Verification Path
Before Team shutdown, Team should prove:
- dataset builder ran and produced records/logs,
- retrieval returns relevant records for demo questions,
- UI renders answer/source/date/evidence cards,
- unknown-question safety works,
- docs reflect the RAG chatbot topic.

Ultragoal should checkpoint those artifacts as durable completion evidence: command outputs, generated dataset summary, screenshots or smoke-test notes, and changed-file list.

## Applied Review Improvements
- Added AI활용도 narrative and optional LLM guarded synthesis from Architect review.
- Added parser-discovery, list-page fallback, crawl logs, rate limiting, and public-only constraints.
- Added runtime real-time crawling as a rejected alternative.
- Added exact verification commands and Definition of Done.
- Clarified sample notices cannot be mixed into real answer corpus without explicit approval.
- Added separate PRD and test-spec artifacts under `.omx/plans/`.
