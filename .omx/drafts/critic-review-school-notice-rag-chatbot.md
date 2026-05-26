# Critic Review — School Notice RAG Chatbot Plan

## Verdict
APPROVE WITH REQUIRED REVISIONS. The plan is viable and grounded in the deep-interview spec, but the final plan must tighten acceptance criteria and verification evidence before handoff.

## Criteria Review

### Principle-option consistency
PASS. Option A aligns with demo stability, bounded crawling, and graceful degradation. The plan should explicitly state how it preserves AI활용도 despite avoiding embedding-first complexity.

### Alternative exploration fairness
PASS WITH NOTE. Options A/B/C are meaningful. Add a concise rejection rationale for runtime real-time crawling because it was a clarified non-goal and is a tempting scope creep path.

### Risk mitigation clarity
REVISE. Risks are identified, but mitigations need to become implementation constraints:
- no private/login data,
- bounded requests/rate delay,
- logs for partial crawl failures,
- fallback answer mode when LLM unavailable,
- no unlabeled synthetic/sample notices in answer corpus without user approval.

### Acceptance criteria testability
REVISE. Most criteria are testable, but “minimum 30 records” can fail for reasons outside implementation. Keep 30 as target, but acceptance should permit lower count only with crawl log evidence and no fabricated real notices. Add a dataset schema validation command/test.

### Verification steps
REVISE. Verification should include concrete commands and expected artifacts, not only manual smoke tests.

## Required Revisions
1. Add a separate `test-spec-school-notice-rag-chatbot.md` artifact with unit/integration/e2e/manual verification.
2. Add exact planned commands:
   - `python scripts/build_dataset.py`
   - `python -m pytest` or equivalent lightweight tests
   - `streamlit run app.py`
3. Add a Definition of Done section.
4. Add a crawler ethics/safety section: public-only, no login, user-provided URLs only, bounded page count, timeout, polite delay.
5. Add AI활용도 explanation into docs step: RAG pipeline, prompt constraints, grounded synthesis, AI usage log.
6. Clarify that sample notices cannot be mixed into the real answer corpus unless explicitly labeled and approved.

## Approval Condition
Approved once the final plan integrates the Architect and Critic improvements and writes both PRD and test-spec artifacts under `.omx/plans/`.
