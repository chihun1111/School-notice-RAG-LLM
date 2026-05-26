# 학교 공지 게시판 RAG AI 챗봇

경동대학교 공개 공지 게시판을 대상으로 **명시적으로 데이터셋을 갱신한 뒤**, 로컬에서 질문에 답하는 데모용 RAG 챗봇입니다. 목표는 대회 발표에서 `크롤링 → 데이터셋 → 검색/RAG → 출처 포함 답변` 흐름을 안정적으로 보여주는 것입니다.

## 핵심 기능

- `config/boards.yaml`에 등록된 6개 공개 공지 URL만 수집합니다.
- `scripts/build_dataset.py`를 직접 실행할 때만 크롤링합니다. 채팅 중 자동/상시 크롤링은 하지 않습니다.
- 공지 데이터는 `data/notices.csv`, `data/notices.jsonl`, `data/crawl_log.jsonl`로 저장됩니다.
- 한국어 질의를 위해 문자 n-gram/키워드, 카테고리/연도 부스트를 결합해 검색합니다. TF-IDF는 `KD_NOTICE_ENABLE_TFIDF=1`일 때만 선택적으로 사용합니다.
- 답변은 제목, 날짜, 원문 링크, 게시판명, 근거 스니펫을 함께 보여줍니다.
- 관련 근거가 부족하면 `수집된 공지 데이터에서 확인되지 않음`으로 안전하게 응답합니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 데이터셋 만들기

```bash
python scripts/build_dataset.py
python scripts/validate_dataset.py
```

생성 파일:

- `data/notices.csv` — 발표/검증용 표 형식 데이터셋
- `data/notices.jsonl` — 앱과 검색 모듈이 읽기 쉬운 JSON Lines 데이터셋
- `data/crawl_log.jsonl` — 보드별 성공/부분 실패/오류 로그

30건 미만으로 수집되면 실제 사이트 구조나 게시글 노출 제한을 `crawl_log.jsonl`에서 확인합니다. 실제 공지처럼 보이는 가짜 데이터는 넣지 않습니다.

## 앱 실행

```bash
streamlit run app.py
```

앱에서 확인할 항목:

1. 데이터셋 상태와 레코드 수가 보이는지 확인
2. 추천 질문 버튼 또는 직접 질문 입력
3. 답변 카드에 출처, 날짜, 원문 링크, 근거 스니펫이 표시되는지 확인
4. 무관한 질문에는 안전한 미확인 답변이 나오는지 확인

## 데모 질문 예시

- 장학금 신청 관련 공지를 알려줘
- 학사 일정이나 수강신청 관련 공지가 있어?
- 취업 또는 채용 관련 최근 공지를 찾아줘
- 학생지원 프로그램 공지를 요약해줘
- 기숙사 고양이 입양 공지가 있어?  ← 안전 미확인 동작 확인용

## 검증 명령

```bash
python scripts/build_dataset.py
python scripts/validate_dataset.py
python scripts/smoke_retrieval.py
python -m pytest
python -m py_compile app.py src/*.py scripts/*.py
```

Streamlit 수동 스모크:

```bash
streamlit run app.py
```

## AI/RAG 구조 설명

1. **수집**: 사용자가 승인한 공개 URL 목록만 대상으로 제한된 페이지 수를 요청합니다.
2. **정규화**: 제목, 카테고리, 날짜, URL, 게시판명, 본문/스니펫을 필수 필드로 저장합니다.
3. **검색**: 한국어 질의를 문자 n-gram과 키워드로 분해하고, 카테고리/연도 힌트를 점수에 반영합니다. 기본 경로는 순수 Python 검색이며, `KD_NOTICE_ENABLE_TFIDF=1` 설정 시에만 TF-IDF를 추가합니다.
4. **답변**: 검색 결과가 임계값 이상일 때만 스니펫 기반 답변을 만들고, 출처를 노출합니다.
5. **안전장치**: 근거가 없으면 추측하지 않고 미확인이라고 답합니다.

## 비목표 / 안전 원칙

- 로그인, 관리자 페이지, 비공개 데이터 접근 금지
- 채팅 런타임에서 지속 크롤링 금지
- 승인되지 않은 URL 추가 수집 금지
- 실제 공지로 오인될 수 있는 합성 데이터 삽입 금지
- 근거 없는 일정/금액/마감일 생성 금지

## 알려진 한계

- 사이트 HTML 구조가 바뀌면 일부 상세 본문 수집이 실패할 수 있습니다.
- 의미 검색 전용 임베딩 모델보다 동의어/긴 문장 추론 성능은 제한적입니다.
- LLM API 연동은 선택 사항이며, 기본 데모는 결정적인 추출형 답변을 사용합니다.
