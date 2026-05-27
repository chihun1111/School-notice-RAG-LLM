# AI 활용 로그 — 학교 공지 게시판 RAG 챗봇

## 목적

대회 제출물에서 AI 활용도와 책임 있는 사용 방식을 설명하기 위한 작업 로그입니다.

## 활용 내역

| 단계 | AI 활용 | 산출물 | 안전/검증 포인트 |
|---|---|---|---|
| 요구사항 정리 | 대화 기반으로 대회 목표, 비목표, 발표 흐름 정리 | `.omx/specs/deep-interview-school-notice-rag-chatbot.md`, 합의 계획 | 로그인/비공개 데이터 제외, 수동 크롤링 원칙 확정 |
| 아키텍처 선택 | Streamlit + 로컬 RAG + 추출형 fallback 비교 | `.omx/plans/consensus-plan-school-notice-rag-chatbot.md` | 외부 API 의존 없이 시연 가능하도록 설계 |
| 크롤러/데이터셋 | 필수 필드와 로그 구조 제안 | `config/boards.yaml`, `scripts/build_dataset.py`, `src/dataset.py` | 승인 URL만 수집, `crawl_log.jsonl`로 실패 원인 기록 |
| 크롤링 범위 확대 | 게시판별 기본 수집 페이지를 3페이지로 확대하고 UI에서 1~10페이지 조정 가능하게 개선 | `config/boards.yaml`, `app.py`, `data/notices.csv`, `data/notices.jsonl` | 2026-05-27 기준 177건 수집, 채팅 중 자동 크롤링은 계속 금지 |
| 학사일정 RAG 추가 | 학사일정 연간 리스트 페이지를 `학사일정` 레코드로 정규화하고 검색 대상에 통합 | `src/crawler.py`, `config/boards.yaml`, `data/notices.csv`, `data/notices.jsonl` | 2026-05-27 기준 학사일정 88건 포함 총 265건 검증, 원문 URL 유지 |
| UI 생각 중 모션 | 답변 생성 중 CSS 애니메이션 상태 표시 추가 | `app.py` | 답변 완료 후 placeholder를 비워 잔상 방지, 테스트로 HTML 상태 문구 확인 |
| 검색/RAG | 한국어 문자 n-gram, 키워드, 카테고리 부스트 설계 | `src/rag.py` | 낮은 점수는 답변 생성 차단 |
| 답변 생성 | 근거 기반 답변 템플릿과 LLM 프롬프트 제약 설계 | `src/answerer.py` | 근거 밖 추측 금지, 출처/스니펫 표시 |
| 선택형 로컬 LLM | Ollama API 연결과 오류 시 추출형 fallback 설계 | `src/ollama_client.py`, `app.py` | 검색된 근거만 전달, localhost 연결 실패 시 답변 생성 중단 없이 fallback |
| 선택형 Gemini API | Gemini REST `generateContent` 연결과 오류 시 추출형 fallback 설계 | `src/gemini_client.py`, `src/answerer.py`, `app.py` | API 키는 환경변수/런타임 입력만 사용, 검색된 근거만 전달 |
| 답변 표시 개선 | 답변 본문을 마크다운 목록으로 정리하고 URL은 출처 카드에만 표시하도록 조정 | `src/answerer.py`, `tests/test_rag_answerer.py` | 모델이 URL을 생성해도 본문에서 제거, 원문 링크는 별도 근거 카드에 유지 |
| 검증/문서화 | 테스트 항목과 README/제출 문서 작성 | `tests/`, `README.md`, 제출용 문서 | 데이터셋 검증, 안전 미확인 응답, 앱 스모크 확인 |

## 프롬프트/정책 원칙

- 답변 생성 프롬프트에는 검색된 근거만 넣습니다.
- Ollama/Gemini 사용 시에도 모델에는 질문과 검색된 근거 스니펫/출처만 전달합니다.
- 답변 본문에는 URL을 넣지 않고, 링크는 출처 카드에서만 보여줍니다.
- 근거가 부족하면 `수집된 공지 데이터에서 확인되지 않음`이라고 답합니다.
- 마감일, 금액, 신청 방법은 스니펫이나 원문에 있을 때만 말합니다.
- 실제 서비스가 아니라 발표용 로컬 데모임을 명시합니다.

## 사람이 확인해야 할 항목

- `data/crawl_log.jsonl`에서 수집 실패/부분 실패가 있는지 확인
- 추천 질문의 답변 출처가 실제 공지 링크로 연결되는지 확인
- 무관한 질문에 공지 내용을 지어내지 않는지 확인
- 제출 전 README와 제출 문서가 현재 구현과 일치하는지 확인
