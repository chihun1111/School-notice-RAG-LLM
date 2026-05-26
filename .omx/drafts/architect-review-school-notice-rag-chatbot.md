# Architect Review — School Notice RAG Chatbot Plan

## Verdict
APPROVE WITH IMPROVEMENTS. The favored architecture is appropriate for a competition MVP, but the plan should explicitly protect the AI활용도 narrative, crawler resilience, and data-source ethics.

## Architectural Soundness
The Streamlit + manual crawler + local dataset + hybrid retrieval design matches the clarified constraints: greenfield project, local demo, no runtime continuous crawling, public URL-only collection, and source-grounded answers. Local JSONL/CSV keeps the system auditable for the report and simplifies failure recovery during presentation.

## Strongest Steelman Counterargument / Antithesis
The strongest counterargument against Option A is that TF-IDF/keyword-heavy retrieval plus extractive fallback may look insufficiently “AI” for a competition whose AI활용도 is 25 points. Judges may view it as a search app unless the answer synthesis layer, prompt constraints, retrieval grounding, and AI-assisted development process are clearly demonstrated. An embedding-first design could make the “RAG” claim more recognizable even if it adds dependency risk.

## Tradeoff Tension
- **Reliability vs AI sophistication:** deterministic local retrieval is demo-safe, but semantic embeddings/LLM synthesis create stronger AI optics.
- **Crawling completeness vs bounded scope:** deep detail crawling improves answer quality but increases parser fragility.
- **Fast implementation vs maintainable architecture:** a single Streamlit file is quick but would make crawler/RAG tests harder.

## Synthesis Path
Keep Option A as baseline, but make the AI layer explicit:
1. Hybrid retrieval is the required fallback.
2. Optional LLM answer synthesis is a first-class module guarded by citations and unknown-answer rules.
3. README/report must explain RAG as retrieval + grounding + constrained generation, not just keyword search.
4. Add a small parser-discovery step before implementation: inspect one board page and one detail page shape, then implement tolerant selectors.
5. Add respectful crawling constraints: bounded pages, timeout, user-agent, rate delay, and no login/private data.

## Required Improvements Before Final Plan
- Add a technical decision that embeddings/LLM are optional enhancement, not required for app viability, while preserving AI활용도 via grounded answer generation and documentation.
- Add crawler resilience details: list-page fallback, detail-page best effort, raw/log record preservation.
- Add rate limiting / public-only crawling constraints.
- Add explicit module test boundaries for crawler, dataset, retrieval, answerer, and UI.
- Add a demo script / presentation path so implementation aligns with 10-minute presentation.
