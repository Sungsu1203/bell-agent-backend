# 개발자 가이드 (chap14_8 · GPT Agent RAG 시스템)

## 1) 폴더 구조 & 의존 규칙
```
agent/                # supervisor, communicator, content_strategist, web_search, vector_search, writers, planner, synthesizer
tools/                # web_rag(검색/로더/인덱싱 파사드), local_rag, loaders, chroma_io
core/                 # config(Env/Flags), llm, routers, state_types, state_io, paths
utils/                # sanitize, outline/text utils, refs, rag_utils(merge/dedupe), writer_scheduler
settings/             # gatekeep 등 정책/화이트리스트
data/, resources/     # 산출물·임시 저장
```
의존 방향(순환 금지):
```
utils → tools → agent
        ↑       │
        └── core┘   # core는 설정·타입·라우팅만 제공
```
- `agent/*` ↔ `agent/*` 직접 import 금지(라우팅은 `core/routers.py`에서).
- `tools/*`는 `utils/*`와 `core.config`만 참조.

## 2) 환경변수 단일화 (`core/config.py`)
- 모든 ENV는 `core/config.py`에서 파싱/검증:  
  `DOC_MODE, AUTO_WRITE_AFTER_RAG, AUTO_WRITE_DURING_RESEARCH, SEARCH_POLICY, SEARCH_MIN_OK, SEARCH_TOPN, CHROMA_NAMESPACE_WEB/LOCAL, GATE_KEEP_SOURCES, ALLOWED_DOMAINS ...`
- 다른 모듈에서 `os.getenv` 직접 호출 금지 → `from core.config import ...`만 사용.

## 3) 공개 API(파사드)만 사용
- `tools/web_rag.py`: `run_search_chain()`, `web_results_to_documents()`, `documents_to_chroma()`만 공개.
- `utils/rag_utils.py`: URL 정규화·디듀프·`merge_refs()` 단일 구현.
- `utils/writer_scheduler.py`: `schedule_writer_if_needed()` 단일 진입.
- 라우팅 분기는 `core/routers.py`에서만.

## 4) 공통 타입/시그니처
- `DocMode = Literal["report","book"]` (`core/state_types.py`)
- `coerce_doc_mode(x) -> DocMode`는 반드시 DocMode 리터럴 반환(문자열 그대로 반환 금지).
- 검색: `run_search_chain(query: str, *, topn: int, policy: str, min_ok: int, gatekeep: bool) -> list[dict]`
- 벡터검색: `retrieve(query: str, *, namespace: str, persist_dir: str, top_k: int) -> list[Document]`
- 병합: `merge_refs(existing: dict|None, new_queries: list[str]|None, new_docs: list|None) -> dict`

## 5) 코드 품질 가드
- pre-commit: Ruff(포맷/심플리파이/정렬), Mypy(타입), Pytest(스모크) 묶기.
- Deptry(의존성 누락/미사용), Radon(복잡도), Vulture(데드 코드) 권장.

## 6) 파일 트리 덤프 & 코드맵 생성
### PowerShell 원클릭 스크립트
```
./make_chap14_8_artifacts.ps1 -RepoRoot "D:\gpt_agent_2025_book"
```
- 산출물:
  - `chap14_8_tree.txt` (UTF-8 BOM)
  - `code_map.svg` (의존 그래프)

### 수동 실행 명령
```powershell
# 트리 덤프
tree .\chap14_8 /f | Out-File -FilePath .\chap14_8_tree.txt -Encoding utf8BOM

# 코드맵 (Graphviz/pydeps 필요)
$env:PYTHONPATH = (Get-Location).Path
python -m pydeps .\chap14_8pp.py --max-bacon 3 -T svg -o .\code_map.svg --noshow `
  --exclude '\.venv|tests|logs|__pycache__|build|dist'
```

## 7) 트러블슈팅
- 폴더명에 `-`(하이픈) 금지 → `chap14_8`처럼 언더스코어 사용(또는 Junction 우회).
- 패키지 인식 안 되면 `__init__.py` 생성.
- `pydeps`가 경로를 모듈로 못 바꾸면: 시작점을 `.\chap14_8pp.py`처럼 **파일 경로**로 지정.
- 브라우저가 SVG를 XML로만 보여주면 VS Code 미리보기로 확인하거나 PNG로 생성:
  `python -m pydeps .\chap14_8pp.py -T png -o code_map.png --noshow`

## 8) PR 운영 순서(권장)
1) config 통합 + import 규칙 강제
2) web_rag 파사드 도입 & 호출부 교체
3) rag_utils 통합(정규화/디듀프/merge_refs 단일 구현)
4) writer_scheduler 단일화
5) routers 가드 정리 & 순환 제거
6) deprecated API 제거

---

© chap14_8 — Developer Guide
