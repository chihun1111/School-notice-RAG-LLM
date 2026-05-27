# 학교 공지 게시판 RAG AI 챗봇

경동대학교 공개 공지 게시판을 대상으로 **명시적으로 데이터셋을 갱신한 뒤**, 로컬에서 질문에 답하는 데모용 RAG 챗봇입니다. 목표는 대회 발표에서 `크롤링 → 데이터셋 → 검색/RAG → 출처 포함 답변` 흐름을 안정적으로 보여주는 것입니다.

## 핵심 기능

- `config/boards.yaml`에 등록된 6개 공개 공지 URL과 학사일정 페이지 1개만 수집합니다.
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

기본 크롤링 범위는 `config/boards.yaml` 기준 **공지 게시판별 최대 3페이지**이며, 학사일정은 연간 리스트 페이지를 함께 수집합니다. 일회성으로 공지 게시판 페이지 수를 더 늘리거나 줄이려면 다음처럼 실행합니다.

```bash
python scripts/build_dataset.py --max-pages 5
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
2. 필요하면 사이드바에서 `보드별 크롤링 페이지 수`를 조정한 뒤 `데이터셋 새로고침`
3. 추천 질문 버튼 또는 직접 질문 입력
4. 답변 카드에 출처, 날짜, 원문 링크, 근거 스니펫이 표시되는지 확인
5. 무관한 질문에는 안전한 미확인 답변이 나오는지 확인

답변 생성 중에는 `근거 검색하고 생각 중` 애니메이션이 표시됩니다.

## 선택: AI 답변 생성 연결

기본 동작은 결정적인 추출형 답변입니다. Ollama 또는 Gemini API를 켜면 검색된 공지/학사일정 근거만 모델에 전달해 자연스러운 한국어 답변으로 문장화하고, 모델이 꺼져 있거나 오류가 나면 자동으로 기존 추출형 답변으로 돌아갑니다. 답변 본문에는 원문 URL을 넣지 않고, 링크는 아래 **출처 및 근거** 카드에서만 보여줍니다.

### Ollama 로컬 LLM

```bash
# 1) 별도 터미널에서 Ollama 실행 및 모델 준비
ollama serve
ollama pull llama3.2

# 2) 앱 실행 터미널에서 Ollama 사용 설정
export KD_NOTICE_LLM_PROVIDER=ollama
export KD_NOTICE_OLLAMA_MODEL=llama3.2
export KD_NOTICE_OLLAMA_BASE_URL=http://localhost:11434

streamlit run app.py
```

### Gemini API

```bash
export KD_NOTICE_LLM_PROVIDER=gemini
export GEMINI_API_KEY=your_api_key_here
export KD_NOTICE_GEMINI_MODEL=gemini-2.5-flash

streamlit run app.py
```

앱 사이드바의 **AI 답변 생성** 설정에서 `추출형만`, `Ollama`, `Gemini API` 중 선택하고 모델명을 직접 수정할 수 있습니다. Gemini API 키는 사이드바 비밀번호 입력칸에 넣거나 `GEMINI_API_KEY` / `GOOGLE_API_KEY` 환경변수로 설정합니다.

지원 환경 변수:

- `KD_NOTICE_LLM_PROVIDER=ollama` 또는 `KD_NOTICE_USE_OLLAMA=1` — Ollama 사용
- `KD_NOTICE_OLLAMA_MODEL` 또는 `OLLAMA_MODEL` — 모델명, 기본값 `llama3.2`
- `KD_NOTICE_OLLAMA_BASE_URL` 또는 `OLLAMA_BASE_URL` — 기본값 `http://localhost:11434`
- `KD_NOTICE_OLLAMA_TIMEOUT` — 요청 제한 시간(초), 기본값 `30`
- `KD_NOTICE_OLLAMA_TEMPERATURE` — 생성 temperature, 기본값 `0.1`
- `KD_NOTICE_OLLAMA_NUM_PREDICT` — 최대 생성 토큰 힌트, 기본값 `512`
- `KD_NOTICE_LLM_PROVIDER=gemini` 또는 `KD_NOTICE_USE_GEMINI=1` — Gemini API 사용
- `KD_NOTICE_GEMINI_API_KEY` 또는 `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY` — Gemini API 키
- `KD_NOTICE_GEMINI_MODEL` 또는 `GEMINI_MODEL` — 모델명, 기본값 `gemini-2.5-flash`
- `KD_NOTICE_GEMINI_TIMEOUT` — 요청 제한 시간(초), 기본값 `30`
- `KD_NOTICE_GEMINI_TEMPERATURE` — 생성 temperature, 기본값 `0.1`
- `KD_NOTICE_GEMINI_MAX_OUTPUT_TOKENS` — 최대 생성 토큰, 기본값 `512`

## 데모 질문 예시

- 장학금 신청 관련 공지를 알려줘
- 학사 일정이나 수강신청 관련 공지가 있어?
- 기말고사 언제야?
- 하계계절학기 수강신청기간 알려줘
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

1. **수집**: 사용자가 승인한 공개 URL 목록만 대상으로 제한된 페이지 수를 요청하고, 학사일정 연간 리스트를 `학사일정` 레코드로 정규화합니다.
2. **정규화**: 제목, 카테고리, 날짜, URL, 게시판명, 본문/스니펫을 필수 필드로 저장합니다.
3. **검색**: 한국어 질의를 문자 n-gram과 키워드로 분해하고, 카테고리/연도 힌트를 점수에 반영합니다. 기본 경로는 순수 Python 검색이며, `KD_NOTICE_ENABLE_TFIDF=1` 설정 시에만 TF-IDF를 추가합니다.
4. **답변**: 검색 결과가 임계값 이상일 때만 스니펫 기반 답변을 만들고, 링크는 답변 본문이 아니라 출처 카드에만 노출합니다.
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
