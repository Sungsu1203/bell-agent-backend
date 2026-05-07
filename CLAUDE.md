# RAG Writer Project (Backend)

## Project context
RAG 기반 광고 에이전시 딜리버리블 생성기. 현재 §12-13 (사용자 검증) 진행 중.

## Source of truth
**Task queue·박제 메모·의사결정 기록은 `README-dev.md` 참조.**
- task 번호 체계: `§<섹션>-<항목>` (예: §12-12-1)
- 작업 시작·완료 시 README-dev.md의 해당 task 섹션 확인 및 갱신
- 종결된 task는 결론과 re-entry 조건을 명시 후 닫음

## Current focus (§12-13)
- 사용자 검증 우선: 일반 LLM Q&A 헬스체크, venfobel 인덱스 직접 QA, end-to-end 리포트 생성
- 백엔드 최적화(§12-12 큐)는 deprioritized

## Environment
- PowerShell (Vertex): `.venv_vertex` + `LLM_PROVIDER=vertexai`
- PowerShell (OpenAI): `.venv_openai` + `LLM_PROVIDER=openai`
- WSL: `python3`
- Provider 토글은 §12-23 박제 참조 (`.env.<provider>` 자동 로드)

## Subagent usage
- 모듈/함수 위치 찾기 → file-explorer
- pytest·평가 로그 요약 → log-summarizer
- 인덱스 메타데이터·저장된 결과 조회 → index-inspector (read-only, 새 retrieval 호출 금지)