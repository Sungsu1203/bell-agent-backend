# RAG Writer Agent (Backend)

## Project context
RAG 기반 딜리버리블 생성기 (LangGraph 멀티에이전트 + FastAPI + ChromaDB + Next.js).
공통 뿌리에서 두 트랙으로 분화 — 각 트랙 상세는 writer_project/ 문서 참조.

## 두 트랙 (source of truth)
- 🏢 회사 트랙 — 광고·마케팅 기획서/보고서 (원형 용도)
  · writer_project/ad/GUARDRAILS.md        = 운영 규칙·상수
  · writer_project/ad/WORKBOARD.md          = 할일·활성 트랙·결정
  · writer_project/ad/README-dev.md, -2.md  = 개선 기록(아카이브)
  · writer_project/ad/README-dev-§14.md     = §14 vertex 백엔드 아카이브
- 📄 논문 트랙 — 학술자료 수집 → 논문 작성 (확장 용도, 현재 활성)
  · writer_project/CLAUDE.md                = 공통 운영 규칙·상수 (자동 로드)
  · writer_project/paper/WORKBOARD.md       = 할일·활성 트랙·결정
  · writer_project/paper/README-dev-paper.md = 종결 catch 아카이브 (§academic + paper-writer)

## Environment (macOS)
- 가상환경: `.venv_vertex/bin/python` (repo 루트 기준). vertex 의존성 = requirements.vertex.txt.
- Provider 토글: `.env.<provider>` 자동 로드 (vertexai / openai).
- zsh: `§`·`*` 포함 경로는 따옴표로 감쌀 것.

## Subagent usage (user 스코프: ~/.claude/agents/)
- 모듈/함수 위치 찾기 → file-explorer
- pytest·평가 로그 요약 → log-summarizer
- 인덱스 메타데이터·저장된 결과 조회 → index-inspector (read-only, 새 retrieval 호출 금지)
