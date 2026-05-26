# PRD — 학교 공지 게시판 RAG AI 챗봇

## Objective
Develop a competition-demo MVP that crawls user-provided public KD University notice boards, builds a local RAG dataset, and answers student-style notice questions with source-grounded Korean responses.

## Users
- Primary: students who want to ask natural-language questions about school notices.
- Secondary: competition judges evaluating 전공연계성, AI활용도, 실무활용성, 창의성, 발표력.

## Problem
School notices are spread across multiple board categories. Students must manually search categories, dates, and titles. A RAG chatbot can reduce search friction while showing trustworthy source evidence.

## Scope
- Manual/test-run crawler for six provided public URLs.
- Local dataset generation.
- Local RAG retrieval and grounded answer display.
- Streamlit demo UI.
- Documentation and submission update.

## Non-goals
- Runtime continuous crawler.
- Private/login notice access.
- User accounts/admin dashboard.
- Production deployment.
- Unapproved synthetic notices in answer corpus.

## Functional Requirements
1. Configure target boards in `config/boards.yaml`.
2. Build dataset with `scripts/build_dataset.py`.
3. Store dataset in CSV/JSONL plus crawl log.
4. Search notices using Korean-friendly hybrid retrieval.
5. Answer with source title, URL, date, and snippet.
6. Provide recommended demo questions.
7. Return safe unknown response for unsupported questions.
8. Document setup, run, AI usage, and demo script.

## Technical Requirements
- Streamlit app entrypoint: `app.py`.
- Modules: `src/crawler.py`, `src/dataset.py`, `src/rag.py`, `src/answerer.py`.
- Required dataset fields: `title`, `category`, `date`, `url`, `source_board`, `content_or_snippet`.
- Optional LLM answerer must be citation-constrained and fallback-safe.

## Acceptance Criteria
See `.omx/plans/consensus-plan-school-notice-rag-chatbot.md#Acceptance-Criteria`.

## Delivery Evidence
- Dataset files and crawl log.
- Test/smoke output.
- Streamlit app run evidence.
- Updated README and submission docs.
