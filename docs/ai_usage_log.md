# AI 활용 내역서 — 경동대학교 공지·학사일정 RAG AI 챗봇

## 1. 문서 목적

AI 전공연계 직무역량 경진대회 제출물 중 **AI 활용 내역서(사용 도구 및 활용 방식 명시, 자율양식)**에 해당하는 문서입니다. 본 프로젝트에서 AI와 자동화 도구를 어떤 단계에서 사용했는지, 그리고 근거 없는 답변을 막기 위해 어떤 안전장치를 적용했는지 정리합니다.

## 2. 프로젝트 개요

- **작품명**: 경동대학교 공지·학사일정 RAG AI 챗봇
- **분야**: IT 분야
- **목표**: 공개 공지/학사일정 데이터를 수집·정제하고, 학생 질문에 대해 출처와 근거가 있는 답변을 제공
- **핵심 AI 방식**: 검색 증강 생성(RAG), 근거 기반 프롬프트, 낮은 관련성 질문 차단

## 3. 사용 AI/자동화 도구

| 도구/기술 | 사용 목적 | 활용 방식 | 결과물 |
|---|---|---|---|
| ChatGPT/Codex | 개발 보조 | 요구사항 정리, 아키텍처 설계, 코드 작성 보조, 테스트/문서 초안 작성 | 코드, README, 제출 문서 |
| 로컬 RAG 검색 모듈 | 관련 공지 검색 | 한국어 문자 n-gram, 키워드, 카테고리/일정 부스트로 질문과 관련된 공지 검색 | `src/rag.py` |
| Ollama(선택) | 로컬 LLM 답변 문장화 | 검색된 근거만 모델에 전달하고 자연어 답변 생성 | `src/ollama_client.py` |
| Gemini API(선택) | 클라우드 LLM 답변 문장화 | 검색된 근거만 전달, 모델별 출력 토큰/thinkingBudget 제한 | `src/gemini_client.py` |
| Python 자동화 | 데이터 수집/검증 | 공개 공지 HTML 파싱, CSV/JSONL 저장, 스모크 테스트 | `scripts/`, `data/`, `tests/` |

## 4. 단계별 AI 활용 내역

| 단계 | AI 활용 | 산출물 | 안전/검증 포인트 |
|---|---|---|---|
| 요구사항 정리 | 대회 목표, 비목표, 발표 흐름 정리 | `.omx/specs/`, `.omx/plans/`, 기획 문서 | 로그인/비공개 데이터 제외, 수동 크롤링 원칙 확정 |
| 아키텍처 선택 | Streamlit + 로컬 RAG + 추출형 fallback 구조 비교 | `README.md`, `app.py` | 외부 API 없이도 시연 가능하도록 설계 |
| 크롤러/데이터셋 | 필수 필드와 로그 구조 설계 보조 | `config/boards.yaml`, `scripts/build_dataset.py`, `src/dataset.py` | 승인 URL만 수집, `crawl_log.jsonl`로 실패 기록 |
| 크롤링 범위 확대 | 게시판별 기본 3페이지, UI 조정 기능 설계 | `config/boards.yaml`, `app.py`, `data/notices.*` | 채팅 중 자동 크롤링 금지 유지 |
| 학사일정 RAG 추가 | 학사일정을 공지 레코드처럼 정규화 | `src/crawler.py`, `data/notices.csv`, `data/notices.jsonl` | 학사일정 88건 포함 총 265건 검증 |
| 검색/RAG | 한국어 문자 n-gram, 키워드, 카테고리/일정 부스트 설계 | `src/rag.py` | 낮은 점수는 답변 생성 차단 |
| 답변 생성 | 근거 기반 답변 템플릿과 LLM 프롬프트 제약 설계 | `src/answerer.py` | 근거 밖 추측 금지, 출처/스니펫 표시 |
| 선택형 로컬 LLM | Ollama API 연결과 오류 시 fallback 설계 | `src/ollama_client.py`, `app.py` | localhost 연결 실패 시 추출형 답변 유지 |
| 선택형 Gemini API | Gemini REST `generateContent` 연결과 오류 시 fallback 설계 | `src/gemini_client.py`, `src/answerer.py`, `app.py` | API 키는 환경변수/런타임 입력만 사용 |
| Gemini 모델별 사용량 설정 | 무료 플랜 사용자를 위해 모델 선택형 UI, API 키 기반 사용 가능 모델 조회, 출력 토큰/thinkingBudget/thinkingLevel 제한 | `src/gemini_client.py`, `app.py`, `tests/test_rag_answerer.py` | 과도한 토큰 입력 clamp, 2.5는 thinkingBudget, 3 계열은 thinkingLevel 적용 |
| 설정창 분리 | Streamlit 기본 개발 툴바를 숨기고 앱 설정을 우측 상단 `⋯` 설정창으로 통합 | `app.py` | 데이터셋/LLM 설정은 dialog 안에서만 노출, 메인 화면은 질문/답변 중심 |
| 답변 표시 개선 | 답변 본문과 출처 카드를 분리 | `src/answerer.py`, `app.py`, `tests/test_rag_answerer.py` | URL은 본문이 아니라 출처 카드에서만 표시 |
| UI 생각 중 모션 | 답변 생성 중 상태 표시 설계 | `app.py` | 답변 완료 후 placeholder 제거 |
| 검증/문서화 | 테스트 항목과 제출 문서 작성 | `tests/`, `README.md`, `AI_Job_Challenge_*.md` | 데이터셋 검증, 안전 미확인 응답, 앱 스모크 확인 |

## 5. 프롬프트/정책 원칙

- 답변 생성 프롬프트에는 검색된 근거만 넣습니다.
- Ollama/Gemini 사용 시에도 질문과 검색된 제목·날짜·스니펫·출처만 전달합니다.
- 근거에 없는 일정, 금액, 장소, 신청 방법은 추측하지 않습니다.
- 관련 근거가 부족하면 `수집된 공지 데이터에서 확인되지 않음`이라고 답합니다.
- 답변 본문에는 URL을 넣지 않고, 링크는 별도 출처 카드에서만 보여줍니다.
- 실제 서비스가 아니라 발표용 로컬 데모임을 명시합니다.

## 6. 데이터 및 개인정보 보호 원칙

- 공개된 경동대학교 공지/학사일정 페이지만 수집합니다.
- 로그인, 관리자 페이지, 비공개 데이터, 개인정보 수집은 하지 않습니다.
- 채팅 질문을 별도 서버에 저장하지 않는 로컬 시연 구조를 기본으로 합니다.
- 데이터셋 갱신은 사용자가 명시적으로 실행할 때만 수행합니다.

## 7. 검증 내역

제출 전 다음 명령으로 검증합니다.

```bash
python3 scripts/validate_dataset.py
python3 scripts/smoke_retrieval.py
python3 -m pytest
python3 -m py_compile app.py src/*.py scripts/*.py
```

수동 검증에서는 장학/학사/취업 질문이 관련 공지를 반환하는지, 무관한 질문이 안전 미확인 답변을 반환하는지 확인합니다.

## 8. 사람이 최종 확인해야 할 항목

- `data/crawl_log.jsonl`에서 수집 실패/부분 실패가 있는지 확인
- 추천 질문의 답변 출처가 실제 공지 링크로 연결되는지 확인
- 무관한 질문에 공지 내용을 지어내지 않는지 확인
- 발표자료와 결과보고서가 현재 구현 범위와 일치하는지 확인
- 제출 마감 전 필수 제출물 3종(결과물/보고서, PPT, AI 활용 내역서)을 모두 준비했는지 확인
