# Deep Interview Context Snapshot — school-notice-rag-chatbot

## Task statement
학교 공지 게시판을 RAG로 하는 AI 챗봇을 만들고 싶다.

## Desired outcome
아직 미확정. 추정상 대회 제출/시연용 또는 실제 학교 공지 검색·질의응답용 챗봇.

## Stated solution
학교 공지 게시판 데이터를 수집/검색하고 RAG로 답변하는 AI 챗봇.

## Probable intent hypothesis
공지사항을 사람이 직접 찾는 불편을 줄이고, 학생이 자연어로 질문하면 관련 공지를 근거와 함께 빠르게 확인하게 하는 실무형 AI 웹서비스를 만들려는 의도.

## Known facts/evidence
- 현재 작업 폴더에는 기획 문서와 제출용 채움본만 있고 구현 코드는 없음.
- 기존 기획은 Streamlit + LLM API + CSV/SQLite 기반 빠른 MVP를 권장함.
- 대회 심사 기준은 전공연계성, AI활용도, 실무활용성, 창의성, 발표력.

## Constraints
- 대회 제출/시연에 맞춘 안정적 MVP가 필요할 가능성이 높음.
- 외부 학교 공지 게시판 접근 방식, 크롤링 허용 여부, 데이터 범위는 미확정.
- 사용할 LLM/API 키 보유 여부 미확정.

## Unknowns/open questions
- 핵심 사용자와 문제 정의.
- 대상 학교/공지 게시판 URL.
- 실시간 크롤링인지 사전 수집 데이터 기반인지.
- 답변에 출처 링크/인용을 필수로 보여줄지.
- 배포/시연 형태.
- 개인정보/로그 저장 범위.

## Decision-boundary unknowns
- 구현 기술스택을 agent가 자동 선택해도 되는지.
- 크롤링 대신 샘플 CSV로 대체해도 되는지.
- LLM API 의존이 허용되는지.

## Likely codebase touchpoints
Greenfield: 새 Streamlit 앱, scraper/ingestion, vector search, prompt/RAG chain, sample data, README/report assets.

## Prompt-safe initial-context summary status
not_needed
