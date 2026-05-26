# Execution-Ready Spec — 학교 공지 게시판 RAG AI 챗봇

## Metadata
- Source workflow: `$oh-my-codex:deep-interview`
- Profile: standard
- Context type: greenfield
- Final ambiguity: 0.10
- Threshold: 0.20
- Readiness: ready for `$ralplan`, `$ultragoal`, `$autopilot`, or `$team` handoff
- Context snapshot: `.omx/context/school-notice-rag-chatbot-20260526T153708Z.md`
- Transcript summary: `.omx/interviews/school-notice-rag-chatbot-20260526T155342Z.md`

## Intent
대회 발표에서 “학교 공지 게시판을 RAG로 검색하고, 근거가 있는 답변을 제공하는 AI 챗봇”을 시연 가능한 MVP로 개발한다. 목표는 실제 운영 서비스가 아니라 전공연계성, AI활용도, 실무활용성, 발표력을 보여주는 안정적인 시연 결과물이다.

## Desired Outcome
사용자가 학교 공지 관련 질문을 입력하면, 앱이 사용자가 지정한 경동대학교 공지 게시판 URL들을 수집해 만든 데이터셋에서 관련 공지를 검색하고, 답변·출처·날짜·근거 문장을 함께 보여준다. 데이터에 없는 질문은 추측하지 않고 모른다고 답한다.

## Target Notice URLs
크롤러는 아래 사용자가 제공한 공개 URL만 대상으로 한다.

1. https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN245
2. https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN246
3. https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN284
4. https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN285
5. https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN286
6. https://www.kduniv.ac.kr/kor/CMS/Board/Board.do?mCode=MN287

Feasibility evidence: local HTTP checks returned 200 for all six URLs, with page titles corresponding to 일반공지, 학사공지, 장학공지, 센터공지, 취업공지, 채용공지.

## In Scope
- Python 기반 MVP 웹앱.
- 사용자가 지정한 URL을 대상으로 한 수동/테스트 실행형 크롤러.
- 크롤링 결과를 정제해 로컬 RAG 데이터셋 생성.
- 공지 제목, 게시판 분류, 작성일, URL, 본문/요약, 근거 스니펫 저장.
- 로컬 검색/RAG 저장소 자동 선택.
- 챗봇 UI 자동 설계.
- 추천 질문 버튼 제공.
- 답변마다 공지명/출처 링크, 작성일/마감일, 근거 문장 표시.
- 데이터에 없는 질문은 추측하지 않고 “현재 수집된 공지 데이터에서 찾을 수 없음”으로 답변.
- 구현 후 기획 문서와 제출용 설명을 RAG 챗봇 주제로 갱신.

## Out of Scope / Non-goals
- 앱 실행 중 상시·실시간 자동 크롤링.
- 로그인/권한이 필요한 비공개 공지 수집.
- 관리자 페이지.
- 사용자 계정, 로그인, 개인화, 즐겨찾기, 알림 기능.
- 개발자가 임의로 다른 학교/게시판 URL을 선택하는 것.
- 실제 운영 서비스 수준의 배포/모니터링.
- 샘플 공지를 실제 공지처럼 위장하는 것.

## Decision Boundaries
OMX/Codex가 확인 없이 결정 가능:
- 기술스택 선택.
- RAG 저장소/검색 방식 선택.
- UI 구성 선택.
- 구현 후 문서 반영.

사용자 확인 필요:
- 크롤링 대상 URL 추가/변경.
- 공개 공지가 부족할 때 답변 데이터셋에 샘플 공지를 실제 답변 근거로 포함할지 여부.
- 로그인 필요한 비공개 데이터 사용.
- 실제 운영 배포 또는 외부 공개.

## Recommended Technical Approach
자동 결정 허용 범위 안에서 권장하는 MVP 조합:

- Web UI: Streamlit
- Crawling: `requests` + `BeautifulSoup4` 기반 공개 게시판 수집
- Dataset: `data/notices.csv` + `data/notices.jsonl`
- Search/RAG store: 로컬 TF-IDF/char n-gram 벡터 검색 또는 경량 임베딩 캐시
- LLM: API 키가 있으면 LLM 답변 생성, 없으면 검색 결과 기반 추출형 답변 fallback
- Config: `config/boards.yaml`에 제공 URL 저장
- Docs: README, 결과보고서/AI 활용 내역서 갱신

Rationale: 대회 시연용 MVP는 무거운 벡터DB/운영 배포보다 “수집→데이터셋→검색→근거 있는 답변” 흐름이 안정적으로 보이는 것이 중요하다.

## Testable Acceptance Criteria
1. `config/boards.yaml` 또는 동등 설정 파일에 6개 대상 URL이 저장되어 있다.
2. 데이터셋 생성 명령을 실행하면 공개 공지 목록/상세에서 최소 30개 이상의 공지 레코드가 생성된다. 사이트 구조상 상세 수집이 막히면 목록 기반 레코드라도 생성하고 실패 이유를 로그에 남긴다.
3. 각 공지 레코드는 최소 `title`, `category`, `date`, `url`, `content_or_snippet`, `source_board` 필드를 가진다.
4. 앱에서 추천 질문 버튼이 보인다.
5. 사용자가 공지 관련 질문을 입력하면 관련 공지 1개 이상을 검색해 답변한다.
6. 답변에는 공지 제목 또는 게시판명, 출처 URL, 작성일 또는 날짜 정보, 근거 스니펫이 표시된다.
7. 수집 데이터에 없는 질문에는 추측 답변 대신 “수집된 공지 데이터에서 확인되지 않음” 유형의 안전 답변을 한다.
8. 크롤러는 앱 런타임에서 무한 반복하지 않고, 사용자가 명시적으로 실행할 때만 데이터셋을 갱신한다.
9. 로그인/비공개 공지는 수집하지 않는다.
10. README 또는 제출용 문서에 RAG 챗봇 주제, 시스템 구조, AI 활용 방식, 검증 방법이 반영된다.

## Assumptions and Resolutions
- Assumption: “실시간 크롤링 제외” means no crawler.  
  Resolution: crawler exists, but as a manually executed dataset builder; app runtime continuous crawling is out of scope.
- Assumption: app can choose any KD University notice board.  
  Resolution: only user-provided URLs may be crawled.
- Assumption: LLM API is always available.  
  Resolution: implementation should support graceful fallback if no API key is present.

## Risks and Mitigations
- Site HTML structure may differ by board: implement tolerant parsers and save raw crawl logs.
- Some dates/deadlines may be in attached files or body text: show 작성일 reliably; deadline extraction is best-effort.
- LLM hallucination risk: force answers to cite retrieved notice snippets; unknown questions must fail safe.
- Korean semantic search quality risk: use char n-gram TF-IDF or hybrid keyword scoring for robust Korean matching in MVP.
- Sample data ambiguity: do not fabricate real notices; only use clearly labeled test fixtures unless user approves sample notices as demo data.

## Suggested File/Folder Shape

```text
.
├── app.py
├── requirements.txt
├── README.md
├── config/
│   └── boards.yaml
├── data/
│   ├── notices.csv
│   ├── notices.jsonl
│   └── crawl_log.jsonl
├── scripts/
│   └── build_dataset.py
├── src/
│   ├── crawler.py
│   ├── dataset.py
│   ├── rag.py
│   └── answerer.py
└── docs/
    └── ai_usage_log.md
```

## Handoff Options

### Recommended: `$ralplan`
Use when architecture/test-shape review should happen before implementation.

```bash
$plan --consensus --direct .omx/specs/deep-interview-school-notice-rag-chatbot.md
```

### Fast implementation: `$ultragoal` or `$autopilot`
Use when the current spec is enough to plan and implement directly.

```bash
$ultragoal .omx/specs/deep-interview-school-notice-rag-chatbot.md
# or
$autopilot .omx/specs/deep-interview-school-notice-rag-chatbot.md
```

### Parallel implementation: `$team`
Use if splitting lanes is useful: crawler/data, RAG/UI, docs/verification.

```bash
$team .omx/specs/deep-interview-school-notice-rag-chatbot.md
```

## Final Readiness Verdict
Development is feasible. The MVP can be implemented as a local Streamlit RAG chatbot with a manually run crawler/dataset builder targeting the provided KD University public notice URLs.
