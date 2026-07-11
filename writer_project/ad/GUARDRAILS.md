# GUARDRAILS — 회사 트랙 (광고·마케팅 기획서/보고서 writer)

> 🏢 회사 트랙 운영 규칙·상수. 공통 규칙(venv·커밋·측정·subagent·방법론)은 상위 `../CLAUDE.md` 참조.
> 여기엔 **회사 트랙에만 해당하는 것**만 적는다.
> 상태: 골격(A안). 회사 트랙 작업 재개 시 채울 것.

---

## 이 트랙이 하는 일
RAG writer agent의 원형 용도 — 광고대행사 기획서·보고서 생성.
(논문 트랙은 이 공통 뿌리에서 학술 논문 작성용으로 확장된 갈래.)

## 회사 트랙 운영규칙 (원본: README-dev.md — 각 항목 상세는 포인터 참조)
> 아래는 한 줄 요약 + 위치 포인터. 상세 아카이브는 `./README-dev.md`에 살아있음.
> ⚠️ 공통 규칙(ENV 4-layer·측정 metric·credential 감사)은 여기 안 둠 → `../CLAUDE.md §6` + `../STANDARDS.md` 지목.

- **폴더 구조 & 의존 규칙** — `utils→tools→agent`, `core`는 설정·타입·라우팅만; `agent/*`끼리 직접 import 금지(라우팅은 `core/routers.py`). [README-dev.md §1]
- **환경변수 단일화** — 모든 ENV는 `core/config.py`(`CFG`)·`ingest_config.py`(`_cfg_*`)에서만 파싱; 타 모듈 `os.getenv` 직접 호출 금지. [README-dev.md §2]
- **RAG 파이프라인 구조** — 수집→변환→인덱싱→검색→드롭필터 흐름; 한국어는 `text-multilingual-embedding-002`(768d), `_looks_like_garbled`로 깨진 바이너리 드롭. [README-dev.md §3]
- **공개 API(파사드)만 사용** — 외부는 `tools/web_rag/__init__.py` 파사드만; 내부 `ingest*.py` 직접 import 금지. [README-dev.md §4]
- **공통 타입/시그니처** — `DocMode` 리터럴, `retrieve()`/`web_search()`/`merge_refs()` 시그니처 고정. [README-dev.md §5]
- **임베딩 안전망** — 기본 fail-fast(RuntimeError); 더미 폴백은 `ALLOW_DUMMY_EMBEDDINGS=1` opt-in만, 프로덕션 금지(인덱스 0벡터 오염 방지). [README-dev.md §6]
- **진단 도구** — `diagnose_embeddings.py`(임베딩·NS 확인)·`diagnose_chunks_deep.py`(청크 분포); 새 토픽 인덱싱 후 1회 권장. [README-dev.md §8]
- **데이터 품질 운영 노하우** — HWP/이벤트·광고/SEO 시장리포트 노이즈 패턴, 단일 호스트 50%↑ 의심, `FILTER_BAD_DOMAINS` 업데이트. [README-dev.md §9]
- **코드 품질 가드** — pre-commit(Ruff·Mypy·Pytest), `tests/` 회귀 스위트(domain_bonus·xlsx·garbled 등). [README-dev.md §10]
- **PR 운영 순서(권장)** — config 통합→파사드→rag_utils→scheduler→routers→토픽 외부화→품질가드→deprecated 제거. [README-dev.md §11]
- **알려진 이슈/주의사항** — 한국어 임베딩 모델 필수(`text-embedding-004` 금지, 변경 시 인덱스 재빌드), `vertex_search.py`는 토글 보존 코드(dead 아님). [README-dev.md §13]
- 디버깅 표준 → `./README-dev-2.md` "디버깅 표준 박제(영구 박제, §14-3 origin)" 참조 (추정 기반 진단 위험성·사전확인 가치·Bash vs PowerShell 등).

## 트랙 전용 상수 (TODO)
- 대상 산출물 포맷(기획서체/보고서체 등):
- 클라이언트·프로젝트별 설정:
- 이 트랙 전용 토픽/프리셋(있다면):

## 측정·품질 기준 (TODO)
- 회사 트랙 산출물 품질 축(있다면):
- 공통 측정 표준은 ../CLAUDE.md 참조.

## 파일 지도
- 이 파일 = 회사 트랙 운영 규칙.
- ./WORKBOARD.md = 회사 트랙 할일·활성 트랙·결정 기록.
- ./README-dev.md, ./README-dev-2.md = 회사 트랙 개선 기록(아카이브).
- ./README-dev-§14.md = §14 vertex 백엔드 점검·개선 아카이브.
