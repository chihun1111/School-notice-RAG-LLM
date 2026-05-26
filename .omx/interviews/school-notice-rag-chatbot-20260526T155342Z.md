# Deep Interview Transcript Summary — School Notice RAG Chatbot

## Metadata
- Profile: standard
- Context type: greenfield
- Final ambiguity: 0.10
- Threshold: 0.20
- Status: ready for planning/execution handoff
- Context snapshot: `.omx/context/school-notice-rag-chatbot-20260526T153708Z.md`

## Rounds

1. **Intent** — 1차 MVP의 핵심 목적
   - Answer: `competition-demo` — 대회 시연용 MVP.
2. **Scope / Non-goals** — 1차 MVP 제외 항목
   - Answer: 앱 실행 중 상시 자동 크롤링 제외, 로그인 공지 제외, 관리자 페이지 제외, 사용자 계정 기능 제외.
   - Later refinement: “실시간 자동 크롤링 제외”는 앱 런타임 상시 크롤링 제외로 재해석. 테스트/시연 준비 단계에서는 크롤러를 실행해 데이터셋을 생성한다.
3. **Outcome / Data source** — 시연용 RAG 데이터 기준
   - Answer: 실제 공지 + 샘플 보강.
   - Later refinement: 사용자가 지정한 URL만 크롤링한다. 개발자가 임의 게시판을 선택하지 않는다.
4. **Success criteria** — RAG 동작 필수 기준
   - Answer: 출처 링크/공지명 표시, 작성일/마감일 표시, 근거 문장 인용, 모르면 모른다고 답변, 추천 질문 버튼.
5. **Decision boundaries** — 자동 결정 허용 범위
   - Answer: 기술스택, RAG 저장소, UI 구성, 구현 후 문서 반영은 자동 결정 가능.
   - Not authorized: 공지 수집 방식 임의 선택, 샘플 공지 임의 작성.
6. **Crawl/sample policy** — 크롤링/샘플 정책
   - Answer: 사용자가 URL 제공.
7. **Target URLs** — 크롤링 대상 URL
   - Answer:
     - https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN245
     - https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN246
     - https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN284
     - https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN285
     - https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN286
     - https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN287

## Pressure-pass finding
Initial assumption was “실시간 자동 크롤링 제외 = no crawler.” User corrected it: MVP should include a crawler that is manually/test-run to build the RAG dataset, while avoiding continuous crawling during normal app runtime.

## Feasibility check
Local `curl` checks returned HTTP 200 for all six provided KD University board URLs. Page titles resolved as 일반공지, 학사공지, 장학공지, 센터공지, 취업공지, 채용공지 under 경동알림/학사안내.
