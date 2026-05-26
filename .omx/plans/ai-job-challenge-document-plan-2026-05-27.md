# AI Job Challenge 문서 작성 계획

## Requirements Summary
- `/Users/chihun/Downloads/AI.pdf`의 공식 공고 내용을 근거로 대회 요건을 반영한다.
- `/Users/chihun/Documents/AI 전공연계 직무역량 경진대회/AI_Job_Challenge_기획_문서.md`의 기존 기획 방향을 유지하되, 제출 준비에 바로 쓸 수 있는 완성형 기획 문서로 정리한다.
- 컴공/IT 분야 주제는 기존 문서의 추천안인 `AI 기반 GitHub/프로젝트 분석 및 직무역량 리포트 생성 웹서비스`를 중심으로 작성한다.

## Acceptance Criteria
- 공식 요건: 참가 대상, 일정, 제출물, 심사 기준, 시상 규모가 PDF와 일치한다.
- 실행 계획: 문제 정의, 해결 아이디어, MVP, 기술스택, AI 활용 계획, 발표/PPT 구성, 결과보고서 구성, 일정, 팀 역할이 포함된다.
- 심사 대응: 전공연계성/AI활용도/실무활용성/창의성/발표력별 점수 확보 전략이 명시된다.
- 제출 준비: 참가신청용 주제 설명, 제출 체크리스트, AI 활용 내역서 예시가 포함된다.

## Implementation Steps
1. PDF를 렌더링/텍스트 추출하여 공식 공고의 핵심 요건을 확인한다.
2. 기존 Markdown 문서 구조와 누락/보완 지점을 확인한다.
3. 기존 내용을 보존하면서 공식 요건과 실행 가능한 제출 준비 항목을 추가·정리한다.
4. Markdown 문법, 핵심 일정/점수/제출물 일치 여부를 검증한다.

## Risks and Mitigations
- PDF 텍스트 추출 품질 저하: 페이지 이미지를 직접 확인하여 핵심 항목을 보정한다.
- 기존 문서 훼손: 단일 Markdown 파일만 수정하고 git diff로 변경 범위를 검토한다.

## Verification Steps
- `grep/sed`로 핵심 항목 존재 확인.
- `git diff --stat` 및 핵심 diff 확인.
- Markdown 코드펜스 균형 검증.
