# scripts/§research-1/run_r3a_straight.py
"""
§research-1 R3-1 (a) — supervisor 우회 **직선 완주** 드라이버.

라운드 없이 한 바퀴:  (섹션마다) references 리셋 → vector_search → section_writer → build_final_report
판정선(D4): missing_titles == 0  AND  섹션별 마커 ≥ 1  AND  원문 대조 표본 2~3건(7번 필수)

설계 근거는 전부 `scripts/output/§research-1/R3a_ENTRYPOINT_RECON.md` 실측이다.
레포 코드 변경 0건 — state 는 그래프 밖에서 이 드라이버가 소유한 dict 다.

┌─ S1~S8 (R3a §5-3) ────────────────────────────────────────────────────────────
│ S1  TOPIC_SLUG assert 를 무거운 import **앞**에        → 모듈 최상단 (import 위)
│ S2  venv = ../.venv_openai/bin/python                  → _check_venv()
│ S3  초기 state = _phase_b_run_inner.py:157-169 템플릿   → build_initial_state()
│ S4  매 회차 pending_write_title/requested_write_title 재세팅 → _run_one_section()
│ S5  flags.completed_sections 루프 간 유지               → 동일 state 재사용(리셋은 references 만)
│ S6  chunk-summary daemon thread join                    → _join_summary_threads()   [= C1]
│ S7  build_final_report → missing_titles 판정            → main() LIVE 구간
│ S8  아웃라인 H3 금지                                    → _read_outline() + _preflight()
├─ C1~C9 (챗 추가) ─────────────────────────────────────────────────────────────
│ C1  종료 전 요약 스레드 join      → S6 와 동일. _join_summary_threads()
│ C2  usage 스냅샷 전후 캡처        → _UsageProbe. **토큰 수만 기록, 단가 곱셈 없음**
│ C3  고아 마커 검사                → _audit_section()  body[[N]] ⊄ sidecar keys
│ C4  미열람 doc 인용 검사          → _audit_section()  sidecar source ⊄ writer 가 본 앞 8건
│ C5  pre-flight 인벤토리 → **STOP** → _preflight()  기존 파일 1건이라도 있으면 SystemExit
│ C6  합계 정합 assert              → _assert_partition()
│ C7  섹션별 references 교체 🔴     → main() 루프 진입부 state["references"] 리셋
│ C7-a RAG_TOP_K 무변경 baseline    → 상향 코드 없음. _preflight() 가 실효값을 출력만
│ C8  각주 종류 분리 집계           → _audit_section()  markers / footnote_defs 별도
│ C9  접힘률 실측 + 섀도 누적       → _RetrieveProbe + shadow_refs
└──────────────────────────────────────────────────────────────────────────────

⚠️ 유료 게이트 2단
  · 기본 = --dry-run (API 호출 0). CLAUDE.md §6 "dry-run 플래그 먼저"
  · 실제 실행은 --live --yes-paid 를 **둘 다** 줘야 한다.

⚠️ C7-a — D4 항목 2가 미달해도 **실측 결과지 드라이버 결함이 아니다.**
   미달 시 튜닝하지 말고 보고하고 STOP 한다(§7 하류 봉합 금지).

사용:
  cd writer_project
  TOPIC_SLUG=experiential-marketing-media ../.venv_openai/bin/python \
      "scripts/§research-1/run_r3a_straight.py" --dry-run
"""
from __future__ import annotations

# ── S1: 무거운 import 앞의 게이트 ────────────────────────────────────────────
#    CLAUDE.md §1 — TOPIC_SLUG 미지정 시 논문 프리셋이 로드된다(catch AB).
#    검증은 실행으로: `env -u TOPIC_SLUG ...` 로 AssertionError 를 확인할 것.
import os

assert os.environ.get("TOPIC_SLUG"), (
    "TOPIC_SLUG 미지정 — 토픽 프리셋 오적용 방지 게이트 (CLAUDE.md §1 / catch AB). "
    "예: TOPIC_SLUG=experiential-marketing-media"
)
TOPIC_SLUG: str = os.environ["TOPIC_SLUG"].strip()

import argparse
import json
import logging
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]          # .../writer_project
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

SUMMARY_THREAD_PREFIX = "chunk-summary-"             # chunk_summary.py:187
EXPECTED_VENV = ".venv_openai"                       # CLAUDE.md §3 — ad/openai 트랙
_MARKER_RE = re.compile(r"\[\[(\d+)\]\]")            # refs.py:29 와 동일
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^(\d+)\]:", re.MULTILINE)   # refs.py:83 과 동일


# ═══════════════════════════════════════════════════════════════════════════
# C6 — 합계 정합 assert (분류형 지표는 각 범주 합 == 전체)
# ═══════════════════════════════════════════════════════════════════════════

def _assert_partition(label: str, total: int, parts: dict[str, int]) -> None:
    """
    분류 결과가 전체를 남김없이 덮는지 확인한다.
    mojibake 376→43 자기검출(R3a §8-3)의 절차화 — 지표를 근거로 쓰기 전에 합을 본다.
    """
    s = sum(parts.values())
    if s != total:
        raise AssertionError(
            f"[C6] 합계 불일치 — {label}: 범주합={s} != 전체={total}  ({parts})\n"
            f"     분류가 전체를 덮지 못한다. 이 지표를 근거로 쓰면 안 된다."
        )
    print(f"   [C6] {label}: {parts} 합={s} == 전체={total} ⭕")


# ═══════════════════════════════════════════════════════════════════════════
# C9 — retrieve 원시 청크 수 포착 (로그 record.args, 문자열 파싱 없음)
# ═══════════════════════════════════════════════════════════════════════════

class _RetrieveProbe(logging.Handler):
    """
    C9 — `_dual_retrieve` 의 반환 청크 수를 로그 record.args 로 집계한다.

    🔴 **계측기는 필터가 아니다.** 이 핸들러는 **관찰만** 하고 어떤 레코드도 폐기하지 않는다.
       (logging 은 핸들러끼리 서로를 막지 않는다. 이전 판의 진짜 문제는 "핸들러를 하나라도
        붙이면 logging.lastResort 가 꺼진다"였고, root 에 핸들러를 명시 부착해 해소한다 — _setup_logging)

    포착 대상 2종 (T10-1 에서 **누락 경로를 발견**해 확장했다):
      ① agent/vector_search.py:597  logger.debug("[dual-retrieve] mode=%s ... → merged=%d | ns_default=%s")
         args = (mode, include_base, top_k, web, local, base, merged, ns_default) → [6] = 청크 수
      ② agent/vector_search.py:585  logger.warning("[dual-retrieve] web/local empty → FALLBACK to base ns='%s' (%d hits)")
         args = (ns_default, hits) → [1] = 청크 수
         🔴 이 경로는 :593 에서 **①의 로그 앞에서 return** 한다. ①만 보면 호출을 통째로 놓친다.
            2026-08-05 실행의 "본선 retrieve 로그 0건"은 이 맹점 때문에 **미호출로 단정할 수 없었다.**

    ⚠️ 문자열 파싱이 아니라 record.args 인덱스로 읽는다(포맷 변경에 덜 취약).
    ⚠️ vector_search 1회 호출에서 여러 쿼리가 돌 수 있어 **합산**한다.
    """
    _MAIN = "[dual-retrieve] mode="
    _FALLBACK = "[dual-retrieve] web/local empty"

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.merged_total = 0
        self.main_hits = 0                            # P-1 — :597 라인 히트 수 (merged 값과 무관)
        self.fallback_hits = 0                        # P-2 — :585 라인 히트 수
        self.fallback_ns: list[str] = []              # P-2 — 그때의 base NS 이름
        self.calls_detail: list[tuple[int, int]] = [] # P-4 — (top_k, merged) 원시 기록
        self.smoke_lines: list[str] = []              # P-3/P-5 — [smoke] 계열 원문

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.msg if isinstance(record.msg, str) else ""
            a = record.args if isinstance(record.args, tuple) else ()
            if msg.startswith(self._MAIN) and len(a) >= 7:
                self.main_hits += 1                                   # P-1 (조건 없이 라인 히트)
                if isinstance(a[6], int):
                    self.merged_total += a[6]
                    self.calls_detail.append((int(a[2]) if isinstance(a[2], int) else -1, int(a[6])))
            elif msg.startswith(self._FALLBACK) and len(a) >= 2:
                self.fallback_hits += 1                               # P-2
                self.fallback_ns.append(str(a[0]))
                if isinstance(a[1], int):
                    self.merged_total += a[1]
                    self.calls_detail.append((-1, int(a[1])))
            elif msg.startswith("[smoke]") or msg.startswith("[smoke]["):
                self.smoke_lines.append(record.getMessage())          # P-3/P-5 원문 그대로
        except Exception:                             # noqa: BLE001  계측이 본선을 막지 않는다
            pass
        # 🔴 폐기 분기 없음. 다른 핸들러(root stream/file)가 동일 레코드를 그대로 출력한다.

    @property
    def calls(self) -> int:
        return self.main_hits + self.fallback_hits

    def snapshot(self) -> dict[str, Any]:
        """P-4 — top_k 축으로 스모크(top_k=1)와 본선(top_k=RAG_TOP_K)을 가른다."""
        smoke_calls = [m for (k, m) in self.calls_detail if k == 1]
        main_calls = [m for (k, m) in self.calls_detail if k > 1]
        unknown = [m for (k, m) in self.calls_detail if k < 0]        # FALLBACK 경로(top_k 미노출)
        return {
            "p1_main_line_hits": self.main_hits,
            "p2_fallback_hits": self.fallback_hits,
            "p2_fallback_ns": list(self.fallback_ns),
            "p4_smoke_calls_topk1": {"n": len(smoke_calls), "merged": smoke_calls},
            "p4_main_calls_topk_gt1": {"n": len(main_calls), "merged": main_calls},
            "p4_fallback_calls_topk_unknown": {"n": len(unknown), "merged": unknown},
            "p3_smoke_lines": list(self.smoke_lines),
        }

    def reset(self) -> None:
        self.merged_total = 0
        self.main_hits = 0
        self.fallback_hits = 0
        self.fallback_ns = []
        self.calls_detail = []
        self.smoke_lines = []


def _setup_logging(log_path: Path) -> None:
    """
    T9-a — 로그 4원칙.
      2) root 에 StreamHandler 를 **명시 부착** → logging.lastResort 의존 제거
      3) 전체 로그를 파일로 저장 → 사후 grep 가능
      4) propagate 유지 (기본 True. 끄지 않는다)

    이전 판의 사고: `agent.vector_search` 에 프로브만 붙였더니 `found>=1` 이 되어
    lastResort 가 꺼졌고, root 에는 핸들러가 없어 **warning 이 전부 사라졌다.**
    그 결과 `[smoke] all queries miss` 를 확인할 방법 자체가 없어졌다.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)            # 콘솔 = INFO 이상(경고 보임)
    sh.setFormatter(fmt)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)           # 파일 = 전량
    fh.setFormatter(fmt)

    root.addHandler(sh)
    root.addHandler(fh)


# ═══════════════════════════════════════════════════════════════════════════
# C2 — usage 스냅샷 (토큰 수만. 단가 곱셈 금지)
# ═══════════════════════════════════════════════════════════════════════════

class _UsageProbe:
    """
    langchain_community 의 get_openai_callback 으로 **본선**(메인 스레드) 토큰을 잡는다.

    🔴 단가를 곱하지 않는다. 단가는 기억값이고, 기억값 곱셈이 R3a §8-3 유형의 사고를 만든다.
       달러 환산은 이 드라이버 밖에서 확정 단가표로 한다.

    🔴 chunk_summary 는 daemon thread + ThreadPoolExecutor 에서 돈다.
       ContextVar 는 스레드에 상속되지 않음을 **실측 확인**했다(2026-08-05):
         main='SET_IN_MAIN' / child='MAIN'
       → 콜백은 **본선만** 포착한다. 요약 몫은 사이드카 실물로 따로 센다.
       이 가정은 live 실행에서 successful_requests 대조로 재검증한다(C6).
    """
    def __init__(self) -> None:
        self.available = False
        self._cm = None
        self.cb = None
        try:
            from langchain_community.callbacks import get_openai_callback
            self._factory = get_openai_callback
            self.available = True
        except Exception as e:                        # noqa: BLE001
            self._factory = None
            print(f"   [C2] usage 콜백 사용 불가 → 토큰 계측 생략: {type(e).__name__}: {e}")

    def __enter__(self):
        if self.available:
            self._cm = self._factory()
            self.cb = self._cm.__enter__()
        return self

    def __exit__(self, *exc):
        if self._cm is not None:
            self._cm.__exit__(*exc)
        return False

    def snapshot(self) -> dict[str, Any]:
        if not self.cb:
            return {"available": False}
        return {
            "available": True,
            "scope": "main-thread only (daemon 요약 스레드 미포착 — ContextVar 미상속 실측)",
            "prompt_tokens": int(getattr(self.cb, "prompt_tokens", 0)),
            "completion_tokens": int(getattr(self.cb, "completion_tokens", 0)),
            "total_tokens": int(getattr(self.cb, "total_tokens", 0)),
            "successful_requests": int(getattr(self.cb, "successful_requests", 0)),
            "note": "단가 곱셈 없음 — 토큰 수만 기록한다",
        }


# ═══════════════════════════════════════════════════════════════════════════
# 사전 점검 (전량 $0)
# ═══════════════════════════════════════════════════════════════════════════

def _check_venv(strict: bool) -> None:
    """S2 — provider 별 venv 분리(STANDARDS §6). .venv_vertex 에는 langchain_openai 가 없다."""
    exe = sys.executable or ""
    if EXPECTED_VENV not in exe:
        msg = f"venv 불일치: sys.executable={exe} (기대: *{EXPECTED_VENV}*)"
        if strict:
            raise SystemExit(f"[FATAL/S2] {msg}")
        print(f"   ⚠️  {msg}")
    else:
        print(f"   ⭕ [S2] venv = {exe}")


def _read_outline(root: Path) -> list[str]:
    """
    S8 — 아웃라인 H2 파싱 + H3 사전 차단.
    report_builder.py:309 는 startswith("##") 이라 ### 도 통과시키고,
    :314 ls[2:] 가 '# 소제목' 을 섹션 제목으로 만든다. 들어오기 전에 막는다.
    """
    p = root / "outlines" / TOPIC_SLUG / "outline_report.md"
    if not p.exists():
        raise SystemExit(f"[FATAL/S8] 아웃라인 부재: {p}")

    titles: list[str] = []
    bad: list[str] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        ls = line.lstrip()
        if not ls.startswith("##"):
            continue
        if ls.startswith("###"):
            bad.append(f"{p.name}:{i} {ls[:60]}")
            continue
        s = ls[2:].strip()
        if s:
            titles.append(s)

    if bad:
        for b in bad:
            print(f"   🔴 [S8] H3 검출: {b}")
        raise SystemExit("[FATAL/S8] 아웃라인에 H3 존재 — report_builder 가 섹션 제목으로 오인한다.")
    print(f"   ⭕ [S8] 아웃라인 H2 {len(titles)}건 / H3 0건")
    return titles


def _inventory_sections(root: Path, titles: list[str]) -> list[dict[str, Any]]:
    """
    C5 — 판정에 개입할 수 있는 파일을 **남김없이** 낸다.

    🔴 스캔 대상은 `report_builder._source_dirs()` 를 **호출해서** 얻는다. 하드코딩하지 않는다.
       사유: `_load_section_body`(report_builder.py:185)가 바로 이 함수의 결과를 순회한다.
             게이트가 소비자와 같은 소스를 봐야 어긋나지 않는다.
       ⚠️ R3a T1 §1-4 의 "ENV 경로는 실질 사문" 기재는 **부정확했다**(2026-08-05 실측 정정).
          죽은 것은 `_source_dirs()` 내부의 `else: os.getenv(...)` **폴백 분기**뿐이고,
          ENV 는 `core/config.py:646 _env_str("REPORT_SOURCES","")` 로 CFG 에 들어가 정상 작동한다.
          실측: REPORT_SOURCES=sections → CFG='sections' → _source_dirs()=['sections']
          → 3곳 하드코딩은 ENV 변경 시 게이트가 조용히 어긋난다. 그래서 호출한다.
    """
    from report_builder import _source_dirs
    from utils.text_utils import section_slug_candidates, section_slugify

    # 어떤 제목이 이 파일명을 주장하는지 역매핑 (파일명 → [제목])
    claim: dict[str, list[str]] = {}
    for t in titles:
        for slug, kind in [(section_slugify(t), "1차조회키")] + \
                          [(c, "폴백후보") for c in section_slug_candidates(t)]:
            claim.setdefault(f"{slug}.md", []).append(f"{kind}:{t[:32]}")

    dirs = _source_dirs()
    print(f"   [C5] 스캔 대상 = _source_dirs() → {dirs}  (하드코딩 아님)")

    out: list[dict[str, Any]] = []
    for dirname in dirs:
        sdir = root / dirname / TOPIC_SLUG
        if not sdir.exists():
            print(f"        · {dirname}/{TOPIC_SLUG}/ — 부재")
            continue
        files = [f for f in sorted(sdir.iterdir()) if f.is_file()]
        print(f"        · {dirname}/{TOPIC_SLUG}/ — {len(files)}건")
        for f in files:
            out.append({
                "dir": dirname,
                "name": f.name,
                "path": str(f.relative_to(root)),
                "bytes": f.stat().st_size,
                "claimed_by": claim.get(f.name, []),
                "head": " ".join(f.read_text(encoding="utf-8", errors="replace").split())[:80]
                        if f.suffix == ".md" else "",
            })
    return out


def _chroma_counts(root: Path) -> dict[str, int]:
    """catch AG — PersistentClient 는 경로 오지정 시 **빈 DB 를 생성**한다. 열기 전에 실재 확인."""
    from tools.web_rag.ingest_vector import _default_chroma_dir

    out: dict[str, int] = {}
    for ns in (f"{TOPIC_SLUG}-web", f"{TOPIC_SLUG}-local"):
        d = _default_chroma_dir(ns)
        if not Path(d).exists():
            out[ns] = -1                              # 부재 — 생성하지 않는다
            continue
        try:
            import chromadb
            out[ns] = int(chromadb.PersistentClient(path=d).get_collection(name=ns).count())
        except Exception as e:                        # noqa: BLE001
            out[ns] = -2
            print(f"   [warn] {ns} 조회 실패: {type(e).__name__}: {e}")
    return out


def _preflight(root: Path, strict_venv: bool) -> dict[str, Any]:
    import core.config as config
    from utils.refs import _cfg_int as _refs_cfg_int

    print("=" * 100)
    print("■ PREFLIGHT ($0)")
    print(f"   ⭕ [S1] TOPIC_SLUG assert 통과 (무거운 import 앞 게이트, 모듈 :52)")
    _check_venv(strict_venv)
    titles = _read_outline(root)

    doc_mode = getattr(config.CFG, "DOC_MODE", "")
    if doc_mode != "report":
        raise SystemExit(f"[FATAL] DOC_MODE={doc_mode!r} != 'report' → section_writer.py:194 조기반환.")
    print(f"   ⭕ DOC_MODE = {doc_mode!r}")
    print(f"   ⭕ TOPIC_SLUG = {TOPIC_SLUG!r}")

    # C7-a — 실효값을 **출력만** 한다. 상향 코드 없음.
    top_k = int(getattr(config.CFG, "RAG_TOP_K", 6))
    preview_max = _refs_cfg_int("REFS_PREVIEW_MAX_DOCS", "REFS_PREVIEW_MAX_DOCS", 8)
    print(f"   ⭕ [C7-a] RAG_TOP_K = {top_k} (무변경 baseline — 상향하지 않는다)")
    print(f"   ⭕ [C4]   REFS_PREVIEW_MAX_DOCS = {preview_max} (writer 가 실제로 보는 참조 수)")

    counts = _chroma_counts(root)
    for ns, c in counts.items():
        tag = "🔴 경로 부재" if c == -1 else ("🔴 조회 실패" if c == -2 else "⭕")
        print(f"   {tag} {ns}: count={c}")

    print(f"\n   [C5] 기존 산출물 인벤토리")
    inv = _inventory_sections(root, titles)

    # 🔴 STOP 판정 기준 = "파일이 있느냐"가 아니라 **"판정에 개입할 수 있느냐"**.
    #    조회는 후보 3종 전부 **정확 파일명 일치**다(core/paths.py:239-243, T5-2 실측으로
    #    prefix·부분문자열·glob 반증 완료). 어느 후보와도 이름이 안 맞는 파일은
    #    `_load_section_body` 가 절대 집어올 수 없으므로 missing_titles 를 오염시키지 못한다.
    #    → claimed_by 가 비면 **보고만**, 차면 **STOP**.
    #    (파일 존재만으로 무조건 STOP 하면 _STALE_ 접두 격리가 무의미해진다)
    interfering = [it for it in inv if it["claimed_by"]]
    inert = [it for it in inv if not it["claimed_by"]]

    for it in interfering:
        print(f"        🔴 [{it['dir']}] {it['name']}  ({it['bytes']}B)")
        print(f"           판정 개입: {it['claimed_by']}")
        if it["head"]:
            print(f"           head: {it['head']}")
    for it in inert:
        print(f"        ⚪ [{it['dir']}] {it['name']}  ({it['bytes']}B) — 조회 후보와 불일치, 개입 불가")

    if interfering:
        # 우회 옵션 없음(D-1). 게이트 옆에 우회구를 두지 않는다 —
        # 유료 실행 직전에 손이 가는 물건이다.
        raise SystemExit(
            f"[STOP/C5] 판정 개입 가능 파일 {len(interfering)}건 → missing_titles 가 오탐이 된다(R3a §8-2).\n"
            f"          삭제는 SIMPLIFY 게이트 소관이므로 드라이버가 하지 않는다. 챗 결정 후 재실행."
        )
    print(f"   ⭕ [C5] 판정 개입 가능 파일 0건"
          + (f" (개입 불가 잔여물 {len(inert)}건은 보고만)" if inert else ""))

    return {"titles": titles, "chroma": counts, "inventory": inv,
            "doc_mode": doc_mode, "rag_top_k": top_k, "refs_preview_max_docs": preview_max}


# ═══════════════════════════════════════════════════════════════════════════
# state 조립 / 실행
# ═══════════════════════════════════════════════════════════════════════════

def build_initial_state(topic_title: str) -> dict[str, Any]:
    """
    T12-1 — `app.py:471-502 initial_state()` 의 **18키 정합**.

    🔴 값은 app 기본값을 **그대로 복사**한다. 우리가 고르지 않는다.
       (T11-3 차집합에서 11키 결손이 나왔다. 그중 messages 시작 메시지와 research_plan 이
        쿼리 관문에 직결됐다. 나머지도 미발견 결손 제거 목적으로 함께 채운다.)
    ⚠️ `refs` 미러 키 포함 — `vector_search.py:1375` 가 `state["refs"]` 를 쓴다.
    ⚠️ app 은 initial_state 를 import 하면 FastAPI 앱이 함께 뜨므로 **리터럴을 복제**한다.
       원본이 바뀌면 여기도 갱신해야 한다(수동 동기 지점).

    S3(_phase_b_run_inner 템플릿) 항목은 app 18키에 흡수됐고,
    드라이버 고유분(topic_title · flags 2키)만 추가로 얹는다.
    """
    import core.config as config
    from core.paths import now_str as _now_str
    from langchain_core.messages import SystemMessage

    doc_mode = getattr(config.CFG, "DOC_MODE", "report")
    default_outline = "outline_report.md" if doc_mode == "report" else "outline.md"

    base: dict[str, Any] = {
        # ── app.py:476-481 ──
        "messages": [SystemMessage(content=(
            f"너희 AI들은 사용자의 요구에 맞는 {('보고서' if doc_mode == 'report' else '책')}을(를) 쓰는 작가팀이다. "
            f"사용자가 사용하는 언어로 대화하라. 현재시각은 {_now_str()}이다. "
            f"항상 한국어로 작성하라. 사용자에게서 한국어/영어가 섞여와도 산출물은 전부 한국어로 통일하라."
        ))],
        "task_history": [],                                              # app:482
        "references": {"queries": [], "docs": []},                       # app:483
        "refs": {"queries": [], "docs": []},                             # app:485  ◀ 미러 키
        "agent_role": str(getattr(config.CFG, "AGENT_ROLE", "") or "").strip().lower(),   # app:488
        "iteration_count": 0,                                            # app:489
        "research_objectives": [],                                       # app:490
        "research_round": 0,                                             # app:491
        "research_loop_active": False,                                   # app:492  ◀ 관문2 조건에 관여
        "findings_md": [],                                               # app:493
        "llm_logs": [],                                                  # app:494
        "new_url_count": None,                                           # app:495
        "topic_slug": getattr(config.CFG, "TOPIC_SLUG", "") or "default",# app:496
        "outline_fname": default_outline,                                # app:497
        "outline_shown": False,                                          # app:498
        "facts_ctx": "",                                                 # app:499
        "research_plan": {"round": 0, "objective": "", "queries": [], "timestamp": _now_str()},  # app:500
        "flags": {},                                                     # app:501
    }
    # ── 드라이버 고유 (app 에 없음) ──
    base["topic_title"] = topic_title
    base["flags"] = {
        "pending_write_title": False,
        "completed_sections": [],                     # S5 — 루프 간 유지(CARRY)
    }
    return base


# ── T9-b: 섹션 간 state 리셋 = **화이트리스트(남길 것 열거)** ──────────────────
#   사유: 이전 판의 C7 은 "지울 것"만 열거해 references 하나만 비웠고,
#         flags["smoke_retrieve_done"](vector_search.py:864)를 빠뜨렸다.
#         → §1 만 스모크를 돌고 §2~7 은 통째로 건너뛰었다(T8 확정).
#   실패 방향을 뒤집는다 — 열거 누락 시
#     · "지울 목록"이면 오염이 **조용히 남고**
#     · "남길 목록"이면 값이 사라져 **즉시 드러난다.**
#   근거는 R3a §4(T4) state 키 표. 재조사하지 않는다.
CARRY_OVER_KEYS = (
    "topic_slug",     # NS 결정 — 없으면 "default" 로 떨어져 인덱스를 못 찾는다 (vector_search.py:715)
    "topic_title",    # 스모크 쿼리 생성원 — 없으면 base_qs 가 비어 스모크 무력화 (vector_search.py:815)
    "outline_fname",  # section_writer 아웃라인 폴백 (section_writer.py:210)
    "agent_role",     # T12-2 — 세션 상수. 섹션마다 바뀔 값이 아니다 (app:488 = CFG.AGENT_ROLE)
)
# T12-2 — T12-1 신규 11키 중 RESET 분류분 (build_initial_state 가 매 회차 재생성).
#   근거는 아래 표. 여기 열거는 **문서용**이며 실제 리셋은 화이트리스트 미포함으로 자동 성립한다.
RESET_KEYS_DOC = (
    "refs",                  # references 미러 — references 와 동시에 비워야 정합 (vector_search.py:1375)
    "research_plan",         # 관문3 소스. planner 는 R3-2 소관 → 매 회차 빈 queries 로 재생성
    "vector_seed_query",     # 🔴 관문2 입력. 섹션마다 값이 달라야 한다 — 이월하면 이전 섹션 제목으로 검색된다
    "research_round", "research_objectives", "research_loop_active",   # 루프 상태 — (a)는 라운드 없음
    "findings_md", "llm_logs", "new_url_count", "outline_shown", "facts_ctx",
    "iteration_count",
)
CARRY_OVER_FLAGS = (
    "completed_sections",   # S5 — 루프 간 유지. section_writer.py:427-430 이 스스로 append
)


def _reset_state_for_section(state: dict[str, Any], topic_title: str) -> dict[str, Any]:
    """화이트리스트만 이월하고 나머지는 build_initial_state() 로 전량 재생성."""
    carried = {k: state[k] for k in CARRY_OVER_KEYS if k in state}
    old_flags = state.get("flags") or {}
    carried_flags = {k: old_flags[k] for k in CARRY_OVER_FLAGS if k in old_flags}

    fresh = build_initial_state(topic_title)
    fresh.update(carried)
    fresh["flags"].update(carried_flags)
    return fresh


def _seed_filter_report(title: str) -> dict[str, Any]:
    """
    R-2 — 제목이 `vector_search.py:1185` 의 3필터를 통과하는지 정적 판정 ($0, 순수 함수).
      if user_q_clean and (not _is_noise_query) and _ok_query and (key not in ran_queries):
          if _looks_like_local_glob: skip
          else: _dual_retrieve(...)          ← 본선 진입
    🔴 제목을 **가공하지 않는다**(T12-3). 번호 접두 제거·번역·확장 전부 금지.
       탈락하면 그것이 결과다.
    """
    # 3필터 중 3개는 utils/query_filters.py 의 모듈 레벨 함수 (vector_search.py:27-30 이 별칭 import)
    from utils.query_filters import (
        strip_web_filters as _strip_web_filters,
        looks_like_local_glob as _looks_like_local_glob,
        ok_query as _ok_query,
    )

    # ⚠️ `_is_noise_query` 는 `vector_search_agent` **안의 중첩 함수**(vector_search.py:1110)라
    #    import 할 수 없다. 본문을 그대로 복제한다 — 원본이 바뀌면 여기도 갱신해야 하는 수동 동기 지점.
    def _is_noise_query(q: str) -> bool:          # ← vector_search.py:1110-1116 복제
        ql = (q or "").strip().lower()
        if ql.rstrip(":;") == "research":
            return True
        if not ql or ql in {"force_query", "force_queries", "force"} or len(ql) <= 2:
            return True
        return any(b in ql for b in ["gtm.js", "function(", "<meta", "<script",
                                     "@media", "var ", "cookieconsent", "usercentrics"])

    cleaned = _strip_web_filters(title)          # 노드가 실제로 거는 전처리와 동일
    noise = bool(_is_noise_query(cleaned))
    ok = bool(_ok_query(cleaned))
    glob = bool(_looks_like_local_glob(cleaned))
    passes = bool(cleaned) and (not noise) and ok and (not glob)
    reasons = []
    if not cleaned: reasons.append("빈 문자열")
    if noise: reasons.append("_is_noise_query=True")
    if not ok: reasons.append("_ok_query=False")
    if glob: reasons.append("_looks_like_local_glob=True")
    return {"title": title, "cleaned": cleaned, "noise": noise, "ok_query": ok,
            "glob": glob, "passes": passes, "reject_reasons": reasons}


def _docs(state: dict[str, Any]) -> list[Any]:
    return list((state.get("references") or {}).get("docs") or [])


def _src_of(doc: Any) -> str:
    """드라이버 자체 비교용 정규화. (refs.py:150 canon 은 본선에선 조건부 사문이나 비교 도구로는 유효)"""
    from utils.refs import _canonicalize_src_for_dedup as canon, _extract_meta
    m = _extract_meta(doc) or {}
    return canon((m.get("source") or m.get("url") or "").strip())


def _join_summary_threads(timeout: float) -> tuple[list[str], bool]:
    """
    S6 / C1 — chunk_summary daemon thread 대기.
    ⚠️ section_writer.py:382 가 start_background_summarization() 반환값을 버려 스레드를 직접 못 받는다(§8-8).
       이름(chunk_summary.py:187 `chunk-summary-<stem>`)으로 찾아 join 한다.
    join 하지 않으면 프로세스 종료 시 요약이 잘리고 **비용 실측도 못 얻는다**(§3-3).
    """
    deadline = time.monotonic() + timeout
    timed_out = False
    while True:
        alive = [t for t in threading.enumerate()
                 if t.name.startswith(SUMMARY_THREAD_PREFIX) and t.is_alive()]
        if not alive:
            break
        if time.monotonic() >= deadline:
            timed_out = True                          # P-2 — 절단 여부를 명시적으로 기록
            break
        for t in alive:
            t.join(timeout=max(0.0, deadline - time.monotonic()))
    left = [t.name for t in threading.enumerate()
            if t.name.startswith(SUMMARY_THREAD_PREFIX) and t.is_alive()]
    if left or timed_out:
        timed_out = True
        print(f"   ⚠️  [S6/C1] 요약 스레드 {len(left)}건 timeout({timeout}s) 미완료: {left}")
        print(f"       🔴 [P-2] 요약 콜 수는 **절단값**이다 — 완결값이 아니다.")
    else:
        print(f"   ⭕ [S6/C1] 요약 스레드 전량 완료 — 요약 콜 수는 완결값")
    return left, timed_out


def resolve_ns_and_dir() -> tuple[str, str]:
    """
    T14-1 — `vector_search_agent:715-722` 의 ns/persist_dir 산출을 그대로 재현한다.
    실증(2026-08-05): run3 로그의 ns_default·ns_web·ns_loc·persist_dir 과 글자 단위 일치.
    ⚠️ ns_web/ns_loc 는 `_dual_retrieve:398-404` 가 CFG 를 직독하므로 **넘기지 않는다.**
    """
    import core.config as config
    from tools.web_rag.utils import sanitize_ns as _san, _resolve_persist_dir as _res
    from tools.web_rag import _default_chroma_dir

    def _cfg_str(name: str, default: str = "") -> str:
        v = getattr(config.CFG, name, None)
        if v is None:
            v = os.getenv(name, default)
        return str(v) if v is not None else default

    slug_raw = (getattr(config.CFG, "TOPIC_SLUG", "") or "default").strip()
    env_ns = (_cfg_str("CHROMA_NAMESPACE", "") or "").strip()
    ns = (_san(env_ns) if env_ns else "") or _san(f"{_san(slug_raw)}-default")
    return ns, _res(ns, _default_chroma_dir(ns))


def _run_retrieve(state: dict[str, Any], query: str, probe: _RetrieveProbe,
                  *, ns_default: str, persist_dir: str, top_k: int) -> int:
    """
    🔴 B안 — `vector_search_agent` **우회**. 함수 층위 직결.

    사유(챗 결정 2026-08-05): "이 노드가 D4 요구 산출물을 생산하는가" 기준.
      · section_writer(마커·사이드카) · build_final_report(missing_titles) = 대체 불가
      · vector_search_agent = `_dual_retrieve` + `merge_refs` 의 래퍼. D4 산출물 0
    ⚠️ 삭제가 아니라 우회다. 챗 UI 경로(graph)는 그대로 둔다.

    이 우회로 함께 사라지는 것(전부 D4 산출물과 무관):
      스모크(:848) · Direct QA 게이트(:926) · user_q/seed 합류(:1161) · QA 요약 반환(:1305/:1342)

    V-1 확인 — `_dual_retrieve(query, *, top_k, ns_default, persist_dir)` (vector_search.py:391)
    V-2 확인 — `merge_refs` 는 `dict(existing or {})` + `.get()` (rag_utils.py:364-366) → `{}` 안전
    """
    from agent.vector_search import _dual_retrieve
    from utils.rag_utils import merge_refs

    probe.reset()
    docs = _dual_retrieve(query, top_k=top_k, ns_default=ns_default, persist_dir=persist_dir) or []
    state["references"] = merge_refs({}, [query], docs)

    print(f"   [T15] _dual_retrieve(query={query!r}, top_k={top_k}, ns_default={ns_default!r})")
    print(f"         → docs {len(docs)}건 → references.docs {len((state['references'] or {}).get('docs') or [])}건")
    return probe.merged_total


def _run_one_section(state: dict[str, Any], title: str) -> float:
    """
    S4 — 매 회차 writer-lock 재세팅.
    section_writer.py:98-101 경로 1(잠금)이 아웃라인 순서를 강제하는 유일한 결정적 수단이다.
    저장 후 :393-401 이 락을 자동 해제하므로 **매번 다시 켠다**.
    """
    from core.models import Task
    from agent.section_writer import section_writer

    flags = state.setdefault("flags", {})
    flags["pending_write_title"] = True
    flags["requested_write_title"] = title

    state.setdefault("task_history", []).append(
        Task(agent="section_writer", done=False, description=f"write: {title}", done_at="")
    )

    t0 = time.monotonic()
    out = section_writer(state) or {}
    elapsed = time.monotonic() - t0
    for k in ("messages", "task_history", "flags", "last_saved_path"):
        if k in out:
            state[k] = out[k]
    return elapsed


def _audit_section(title: str, saved: str, seen_sources: list[str]) -> dict[str, Any]:
    """
    C3 · C4 · C8 — 저장된 섹션 실물을 대조한다.

    C8  [[N]] 마커 수와 [^N]: auto footnote 수를 **따로** 센다.
        AUTO_FOOTNOTE 기본 True(config.py:503)라 마커 0건 섹션에도 각주가 붙는다(T6-2).
        → D4 항목 2는 [[N]] + .refs.json 키만 인정. [^N]: 은 불인정.
    C3  본문 [[N]] ⊄ sidecar 키  = 고아 마커. 원인 후보 refs.py:458(>20) · :471(url 없음)
    C4  sidecar 의 source ⊄ writer 가 본 앞 N건 = **본 적 없는 doc 인용**.
        C3 와 방향이 반대다(C3=키 없음 / C4=키는 있는데 미열람).
    """
    r: dict[str, Any] = {"title": title, "saved": saved,
                         "markers": [], "orphan_markers": [], "footnote_defs": [],
                         "sidecar": "", "sidecar_keys": [], "unseen_cited": []}
    if not saved or not Path(saved).exists():
        r["error"] = "저장 파일 없음"
        return r

    body = Path(saved).read_text(encoding="utf-8")
    r["markers"] = sorted({int(m) for m in _MARKER_RE.findall(body)})
    r["footnote_defs"] = sorted({int(m) for m in _FOOTNOTE_DEF_RE.findall(body)})   # C8

    sp = Path(saved).with_suffix(".refs.json")
    sidecar: dict[str, Any] = {}
    if sp.exists():
        r["sidecar"] = str(sp)
        try:
            sidecar = json.loads(sp.read_text(encoding="utf-8"))
        except Exception as e:                        # noqa: BLE001
            r["error"] = f"사이드카 파싱 실패: {type(e).__name__}"
            sidecar = {}
    keys = sorted({int(k) for k in sidecar if str(k).isdigit()})
    r["sidecar_keys"] = keys

    r["orphan_markers"] = [n for n in r["markers"] if n not in set(keys)]           # C3

    from utils.refs import _canonicalize_src_for_dedup as canon
    seen = set(seen_sources)
    for k, v in sidecar.items():
        s = canon(((v or {}).get("source") or (v or {}).get("url") or "").strip())
        if s and s not in seen:
            r["unseen_cited"].append({"marker": k, "source": s})                   # C4
    return r


# ═══════════════════════════════════════════════════════════════════════════
# D-3 — D4 항목 3 원문 대조 표본 사전 지정
# ═══════════════════════════════════════════════════════════════════════════

def _designate_samples(titles: list[str]) -> list[dict[str, Any]]:
    """
    실행 **전에** 표본을 못박는다. 결과를 보고 고르면 유리한 섹션만 고르게 된다.

      ① 섹션 7 「실행 로드맵 및 KPI 설정」 — 처방형. 코퍼스에 근거 부재 예상 지점. **필수**
      ② 섹션 6 「미디어 형식별 체험 설계와 최신 동향」 — 접힘 누적 최대 지점
         ⚠️ 사유 변경 명시: 원래 사유였던 "교차 섹션 오염"은 **C7(섹션별 references 교체)이 해소**했다.
            현 사유는 오염이 아니라 **접힘**이다(R3a §8-3 — 같은 URL 청크가 refs 1건으로 접힘).
      ③ 마커 수 최소 섹션 — 실행 후 자동 선정(사전 지정 불가)
         🔴 [P-1] 동점 처리 규칙: 마커 수 최소가 **복수면 섹션 번호가 큰 쪽**을 택한다.
            사후 자의 개입을 차단하기 위해 규칙을 실행 전에 못박는다.
    """
    out: list[dict[str, Any]] = []
    idx7 = 7 - 1
    idx6 = 6 - 1
    if idx7 < len(titles):
        out.append({"tag": "①", "title": titles[idx7], "why": "처방형 — 코퍼스 근거 부재 예상 지점 (필수)"})
    if idx6 < len(titles):
        out.append({"tag": "②", "title": titles[idx6],
                    "why": "접힘 누적 최대 지점 (사유 변경: 원 사유 '교차 섹션 오염'은 C7이 해소)"})
    out.append({"tag": "③", "title": None,
                "why": "마커 수 최소 섹션 — 실행 후 자동 선정 (동점 시 섹션 번호가 큰 쪽, P-1)"})
    return out


# ═══════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser(description="§research-1 R3-1 (a) 직선 완주 드라이버")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True, help="기본. API 호출 0")
    g.add_argument("--live", action="store_true", help="실제 실행(유료). --yes-paid 동반 필수")
    ap.add_argument("--yes-paid", action="store_true", help="유료 실행 명시 승인 (2단 게이트)")
    ap.add_argument("--max-sections", type=int, default=7)
    ap.add_argument("--summary-timeout", type=float, default=300.0)
    ap.add_argument("--no-strict-venv", dest="strict_venv", action="store_false", default=True)
    # D-1: --allow-existing-sections 우회구는 **의도적으로 없다**.
    #      C5 는 게이트다. 게이트 옆에 우회구를 두면 유료 실행 직전에 손이 간다.
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    live = bool(args.live)
    root = _REPO
    os.chdir(root)                                    # 상대경로(outlines/, sections/) 기준 고정
    run_ts = time.strftime("%Y%m%d-%H%M%S")
    log_path = root / "scripts" / "output" / "§research-1" / f"R3a_run_{run_ts}.log"

    print(f"\n§research-1 R3-1 (a) 직선 완주 드라이버 — mode={'LIVE(유료)' if live else 'DRY-RUN($0)'}")
    pre = _preflight(root, args.strict_venv)
    titles: list[str] = pre["titles"][: max(0, args.max_sections)]
    preview_max: int = pre["refs_preview_max_docs"]
    samples = _designate_samples(titles)

    import core.config as config
    topic_title = (getattr(config.CFG, "TOPIC_TITLE", "") or TOPIC_SLUG).strip()
    state = build_initial_state(topic_title)
    ns_default, persist_dir = resolve_ns_and_dir()          # T14-1
    top_k_eff = int(pre["rag_top_k"])                       # C7-a — 무변경 baseline (6)

    # ── DRY-RUN 게이트 ──────────────────────────────────────────────────────
    if not live:
        print("\n" + "=" * 100)
        print("■ DRY-RUN — 실행 계획 (API 호출 0건)")
        print(f"   topic_title = {topic_title!r}")
        print(f"   초기 state  = keys={sorted(state)}  refs.docs={len(_docs(state))}")
        print(f"\n   섹션 {len(titles)}건 — 매 회차 [C7] references 리셋 후 전용 retrieve:")
        for i, t in enumerate(titles, 1):
            print(f"     {i}. {t}")
        print("\n   예상 유료 호출:")
        print(f"     · vector_search_agent : {len(titles)}회 (섹션당 1회 — C7)")
        print(f"     · section_writer LLM  : {len(titles)}회")
        print(f"     · chunk_summary 요약  : 최대 {len(titles)} × {preview_max} = {len(titles) * preview_max}회")
        print(f"       (상한 {preview_max} = REFS_PREVIEW_MAX_DOCS. build_marker_refs_map 의 20 은 뒤에 있어 안 걸린다)")
        print("\n   계측 (전부 드라이버 측, 레포 변경 0):")
        print("     · [C2] 토큰 수 — 본선만 포착. 요약 몫은 사이드카 실물로 분리. **단가 곱셈 없음**")
        print("     · [C9] 섹션마다 (retrieve 반환 청크 수, refs 건수, 고유 URL 수) + 섀도 누적")
        print("     · [C3] 고아 마커 / [C4] 미열람 doc 인용 / [C8] 마커 vs 각주 분리")
        print("     · [C6] 분류형 지표 합계 정합 assert")
        print("\n   [D-3] D4 항목 3 원문 대조 표본 — **실행 전 지정**:")
        for s in samples:
            print(f"     {s['tag']} {s['title'] or '(실행 후 자동 선정)'}")
            print(f"        사유: {s['why']}")

        # 🔴 dry-run 에서도 로깅 기구를 **실제로 세워 검증**한다.
        #    "경로를 출력했다"가 아니라 "파일이 실제로 생겼다"까지 확인해야
        #    유료 실행에서 로그가 또 사라지는 사고를 사전에 배제할 수 있다. ($0)
        print(f"\n   [T9-a] 전체 로그 파일 — dry-run 에서 실제 생성 검증:")
        _setup_logging(log_path)
        logging.getLogger("agent.vector_search").warning(
            "[dry-run] 로깅 기구 검증용 warning — 이 줄이 파일에 있어야 한다")
        for h in logging.getLogger().handlers:
            try: h.flush()
            except Exception: pass
        exists = log_path.exists()
        size = log_path.stat().st_size if exists else 0
        print(f"      경로     : {log_path}")
        print(f"      생성 여부: {'⭕ 생성됨' if exists else '🔴 미생성'}  size={size}B")
        if exists and size > 0:
            print(f"      첫 줄    : {log_path.read_text(encoding='utf-8').splitlines()[0]}")
        print(f"      root 핸들러 = {[type(h).__name__ for h in logging.getLogger().handlers]}")
        print(f"      propagate(agent.vector_search) = {logging.getLogger('agent.vector_search').propagate}")
        print(f"      · 프로브는 관찰만 하고 레코드를 폐기하지 않는다")
        print(f"      · [dual-retrieve] 포착 2종 (main :597 + FALLBACK :585) — T10-1 맹점 보정")
        if not (exists and size > 0):
            raise SystemExit("[STOP/T9-a] 로그 파일이 생성되지 않았다 — 유료 실행 진입 금지.")
        print(f"\n   [T12-1] build_initial_state() 키 {len(state)}개 (app.py:471-502 정합):")
        print(f"      {sorted(state.keys())}")
        print(f"\n   [T9-b/T12-2] 섹션 간 state = 화이트리스트 이월:")
        print(f"      CARRY keys  = {sorted(CARRY_OVER_KEYS)}")
        print(f"      CARRY flags = {sorted(CARRY_OVER_FLAGS)}")
        print(f"      RESET(문서) = {sorted(RESET_KEYS_DOC)}")
        print(f"      그 외 전량 build_initial_state() 재생성 (flags.smoke_retrieve_done 포함)")

        # 조건 (e) — 7개 _dual_retrieve 호출의 (query, top_k, ns_default) 전부 명시
        print(f"\n   [T15/B안] vector_search_agent **우회** — _dual_retrieve 직접 호출 7건:")
        print(f"      ns_default  = {ns_default!r}")
        print(f"      persist_dir = {persist_dir}")
        print(f"      (ns_web/ns_loc 는 _dual_retrieve:398-404 가 CFG 직독 — 인자 아님)")
        for i, t in enumerate(titles, 1):
            fr = _seed_filter_report(t)
            print(f"      {i}. _dual_retrieve(query={t!r}, top_k={top_k_eff}, ns_default={ns_default!r})")
            print(f"         → merge_refs({{}}, [{t!r}], docs) → state['references']"
                  f"   (참고: 구 필터 통과={fr['passes']}, 우회로에선 게이트 아님)")
        print(f"      ⇒ 우회로 제거되는 경로: 스모크(:848) · Direct QA 게이트(:926) · "
              f"user_q/seed 합류(:1161) · QA 요약 반환(:1305/:1342)")

        print("\n   ⚠️ [C7-a] RAG_TOP_K 무변경 baseline.")
        print("      D4 항목 2가 미달해도 그것은 실측 결과다. 튜닝하지 말고 보고하고 STOP 한다.")
        print("\n🛑 STOP 게이트 — 코드 변경 0 · 커밋 0 · 유료 호출 0 확인됨.")
        print("   실행하려면: --live --yes-paid")
        return 0

    if not args.yes_paid:
        raise SystemExit("[FATAL] --live 에는 --yes-paid 가 필요하다 (유료 2단 게이트).")

    # ── LIVE ────────────────────────────────────────────────────────────────
    # T9-a — root 핸들러 **먼저** 부착. 그 다음 프로브(관찰자)를 얹는다.
    _setup_logging(log_path)
    probe = _RetrieveProbe()
    vs_logger = logging.getLogger("agent.vector_search")
    vs_logger.addHandler(probe)
    vs_logger.setLevel(logging.DEBUG)                 # [dual-retrieve] 는 debug 레벨
    assert vs_logger.propagate, "propagate 가 꺼지면 root 핸들러로 안 간다"   # T9-a-4
    print(f"   [T9-a] 전체 로그 → {log_path}")
    logging.getLogger(__name__).warning("[R3a] live 실행 시작 — 로그 부착 확인용 warning")

    print("\n" + "=" * 100)
    print("■ LIVE 실행 시작")
    t_start = time.monotonic()
    rows: list[dict[str, Any]] = []
    shadow: dict[str, Any] = {"queries": [], "docs": []}      # C9 — writer 에 안 먹이는 섀도 누적

    with _UsageProbe() as usage:
        from utils.rag_utils import merge_refs as _merge_refs

        for i, title in enumerate(titles, 1):
            print(f"\n── [{i}/{len(titles)}] {title}")

            # 🔴 C7 + T9-b — 화이트리스트 이월 외 전량 재생성.
            #    references 만 비우던 이전 판이 smoke_retrieve_done 을 남겨 §2~7 을 죽였다(T8).
            state = _reset_state_for_section(state, topic_title)
            print(f"   [T9-b] state 재생성 — carry={sorted(CARRY_OVER_KEYS)} "
                  f"+ flags{sorted(CARRY_OVER_FLAGS)}(={len(state['flags'].get('completed_sections') or [])}건)")

            # T15 — vector_seed_query 제거(B안에서 불요). 제목을 쿼리로 **verbatim** 사용.
            fr = _seed_filter_report(title)          # 참고 지표로만 유지(우회로에선 게이트 아님)
            raw_chunks = _run_retrieve(state, title, probe,
                                       ns_default=ns_default, persist_dir=persist_dir, top_k=top_k_eff)
            docs_now = _docs(state)
            uniq = len({_src_of(d) for d in docs_now if _src_of(d)})
            fold = (1 - len(docs_now) / raw_chunks) if raw_chunks else None
            snap = probe.snapshot()
            print(f"   [C9] retrieve 청크={raw_chunks}  refs={len(docs_now)}  고유URL={uniq}"
                  + (f"  접힘률={fold:.1%}" if fold is not None else "  접힘률=n/a"))
            print(f"   [P-1] :597 라인 히트 = {snap['p1_main_line_hits']}회")
            print(f"   [P-2] :585 FALLBACK  = {snap['p2_fallback_hits']}회  ns={snap['p2_fallback_ns']}")
            print(f"   [P-4] top_k=1(스모크) {snap['p4_smoke_calls_topk1']['n']}콜 merged={snap['p4_smoke_calls_topk1']['merged']}"
                  f" / top_k>1(본선) {snap['p4_main_calls_topk_gt1']['n']}콜 merged={snap['p4_main_calls_topk_gt1']['merged']}"
                  f" / FALLBACK(top_k 미노출) {snap['p4_fallback_calls_topk_unknown']['n']}콜")
            print(f"   [P-3] [smoke] 라인 {len(snap['p3_smoke_lines'])}건:")
            for ln in snap["p3_smoke_lines"]:
                print(f"        · {ln}")

            shadow = _merge_refs(shadow, list((state["references"] or {}).get("queries") or []), docs_now)

            # C4 — writer 가 실제로 보는 앞 N건을 write **전에** 확정 (refs.py:320 docs[:max_docs])
            seen_sources = [_src_of(d) for d in docs_now[:preview_max]]
            seen_sources = [s for s in seen_sources if s]

            # R-3 — writer 에 들어갈 [이전 대화] 실물. QA 산문이 사라졌는지가 이번 판별축.
            _msgs = state.get("messages") or []
            _mtypes = [type(m).__name__ for m in _msgs]
            _qa_marks = sum(1 for m in _msgs
                            if (getattr(m, "additional_kwargs", {}) or {}).get("qa_direct_reply"))
            print(f"   [R-3] messages {len(_msgs)}건 {_mtypes}  / qa_direct_reply 마킹 {_qa_marks}건")

            elapsed = _run_one_section(state, title)
            saved = state.get("last_saved_path") or ""
            audit = _audit_section(title, saved, seen_sources)
            audit.update({
                "order": i,                           # 동점 처리용 섹션 번호
                "probe": snap,                        # P-1~P-4 원시 기록
                "seed_filter": fr,                    # R-2
                "msgs_before_write": {"n": len(_msgs), "types": _mtypes, "qa_marked": _qa_marks},  # R-3
                "elapsed_s": round(elapsed, 1), "raw_chunks": raw_chunks,
                "refs_docs": len(docs_now), "unique_urls": uniq,
                "fold_rate": None if fold is None else round(fold, 4),
                "seen_sources_n": len(seen_sources),
            })
            rows.append(audit)

            print(f"   [write] {audit['elapsed_s']}s  saved={saved or '(저장 실패)'}")
            print(f"   [C8] 본문 마커 {len(audit['markers'])}개 {audit['markers']}"
                  f"  /  auto 각주 {len(audit['footnote_defs'])}개  (별도 집계)")
            print(f"   [C3] 사이드카 키 {len(audit['sidecar_keys'])}개"
                  f"  고아 마커 {len(audit['orphan_markers'])}개 {audit['orphan_markers'] or ''}")
            print(f"   [C4] 미열람 doc 인용 {len(audit['unseen_cited'])}건 "
                  f"{[u['marker'] for u in audit['unseen_cited']] or ''}")

    print("\n■ 요약 스레드 대기 (S6/C1)")
    stuck, summary_join_timeout = _join_summary_threads(timeout=args.summary_timeout)

    # 요약 실제 발생 건수 — 사이드카 실물 (C2 분리 몫)
    summarized = 0
    for r in rows:
        if r.get("sidecar") and Path(r["sidecar"]).exists():
            try:
                sc = json.loads(Path(r["sidecar"]).read_text(encoding="utf-8"))
                summarized += sum(1 for v in sc.values() if (v or {}).get("summary"))
            except Exception:                         # noqa: BLE001
                pass

    # S7 — build_final_report. 최종 서지는 누적 state["references"] 를 읽지 않는다(§8-7)
    print("\n■ build_final_report (S7)")
    from report_builder import build_final_report
    final_path, missing = build_final_report(TOPIC_SLUG)
    elapsed_total = time.monotonic() - t_start
    print(f"   final_path     = {final_path}")
    print(f"   missing_titles = {len(missing)}건 {missing if missing else ''}")

    # ── C6 합계 정합 ────────────────────────────────────────────────────────
    print("\n■ [C6] 합계 정합 assert")
    total_markers = sum(len(r["markers"]) for r in rows)
    _assert_partition("마커 분류(사이드카 매칭 vs 고아)", total_markers, {
        "사이드카_매칭": sum(len(set(r["markers"]) - set(r["orphan_markers"])) for r in rows),
        "고아": sum(len(r["orphan_markers"]) for r in rows),
    })
    _assert_partition("섹션 분류(마커≥1 vs 마커0)", len(rows), {
        "마커있음": sum(1 for r in rows if r["markers"]),
        "마커없음": sum(1 for r in rows if not r["markers"]),
    })
    _assert_partition("섹션 분류(저장성공 vs 실패)", len(rows), {
        "저장성공": sum(1 for r in rows if r.get("saved")),
        "저장실패": sum(1 for r in rows if not r.get("saved")),
    })

    # ── D4 판정 ─────────────────────────────────────────────────────────────
    no_marker = [r["title"] for r in rows if not r["markers"] or not r["sidecar_keys"]]
    orphans = [r["title"] for r in rows if r["orphan_markers"]]
    unseen = [r["title"] for r in rows if r["unseen_cited"]]
    ok_missing = (len(missing) == 0)
    ok_marker = (not no_marker) and (not orphans)

    print("\n" + "=" * 100)
    print("■ D4 판정  (마커는 [[N]] + .refs.json 키만 인정 — [^N]: 불인정, C8)")
    print(f"   {'⭕' if ok_missing else '🔴'} ① missing_titles == 0")
    print(f"   {'⭕' if ok_marker else '🔴'} ② 섹션별 마커 ≥ 1 + 고아 0"
          + (f"  (마커0: {no_marker})" if no_marker else "")
          + (f"  (고아: {orphans})" if orphans else ""))
    print(f"   {'⭕' if not unseen else '🔴'} [C4] 미열람 doc 인용 0"
          + (f"  ({unseen})" if unseen else ""))
    # ── D-3 표본 3건 강조 출력 ──────────────────────────────────────────────
    by_title = {r["title"]: r for r in rows}
    # P-1 — 마커 수 최소. 동점이면 **섹션 번호가 큰 쪽**(-order 로 tie-break). 사후 자의 개입 차단.
    min_row = min(rows, key=lambda r: (len(r["markers"]), -r["order"])) if rows else None
    for s in samples:
        if s["tag"] == "③":
            if min_row:
                tied = [r["order"] for r in rows if len(r["markers"]) == len(min_row["markers"])]
                s["title"] = min_row["title"]
                s["why"] = (f"마커 수 최소 = {len(min_row['markers'])}개"
                            + (f" / 동점 {sorted(tied)} → 번호 큰 §{min_row['order']} 선택 (P-1)"
                               if len(tied) > 1 else ""))
            else:
                s["title"], s["why"] = None, "행 없음"

    print("\n   ⏸ ③ 원문 대조 표본 — **수동 대조 대상 (D-3, 실행 전 지정)**")
    print("   " + "━" * 92)
    for s in samples:
        r = by_title.get(s["title"] or "")
        print(f"   {s['tag']}  {s['title'] or '(선정 실패)'}")
        print(f"       사유    : {s['why']}")
        if r:
            print(f"       사이드카: {r['sidecar'] or '(없음)'}")
            print(f"       섹션파일: {r['saved'] or '(저장 실패)'}")
            print(f"       마커 {len(r['markers'])}개 / auto각주 {len(r['footnote_defs'])}개"
                  f" / 고아 {len(r['orphan_markers'])} / 미열람인용 {len(r['unseen_cited'])}")
        else:
            print(f"       ⚠️ 해당 섹션 결과 없음")
    print("   " + "━" * 92)

    print("\n   (참고) 전 섹션 사이드카:")
    for r in rows:
        if r.get("sidecar"):
            print(f"        {r['title'][:38]:40s} → {r['sidecar']}")

    print("\n■ 관측")
    # P-5 — 스모크는 매 섹션 동일 쿼리 3건이 도는 구조다. 7회 결과가 같은가만 본다(해석 없음).
    smoke_sets = [tuple(r["probe"]["p3_smoke_lines"]) for r in rows]
    uniq_smoke = {s for s in smoke_sets}
    print(f"   [P-5] 스모크 결과 집합 — 섹션 {len(smoke_sets)}개 중 서로 다른 집합 {len(uniq_smoke)}종")
    print(f"        판정: {'전량 동일' if len(uniq_smoke) <= 1 else '상이 있음'}")
    if len(uniq_smoke) > 1:
        for idx, s in enumerate(smoke_sets, 1):
            print(f"        §{idx}: {list(s)}")
    print(f"   [P-1] 섹션별 :597 히트 = {[r['probe']['p1_main_line_hits'] for r in rows]}")
    print(f"   [P-2] 섹션별 :585 FALLBACK = {[r['probe']['p2_fallback_hits'] for r in rows]}")
    print(f"   [P-4] 섹션별 (스모크콜, 본선콜, FALLBACK콜) = "
          f"{[(r['probe']['p4_smoke_calls_topk1']['n'], r['probe']['p4_main_calls_topk_gt1']['n'], r['probe']['p4_fallback_calls_topk_unknown']['n']) for r in rows]}")
    print(f"   [C9] 접힘률 곡선 = {[r['fold_rate'] for r in rows]}")
    print(f"   [C9] 섀도 누적 refs.docs = {len(shadow.get('docs') or [])}  (writer 미노출)")
    u = usage.snapshot()
    print(f"   [C2] usage = {u}")
    print(f"   [C2] chunk_summary 요약 성공 = {summarized}건 (사이드카 실물 — 콜백 미포착 몫)"
          + ("  🔴 [P-2] **절단값**(join timeout)" if summary_join_timeout else "  ⭕ 완결값"))
    if u.get("available"):
        print(f"        대조: successful_requests={u['successful_requests']} vs "
              f"본선 예상={len(titles)}(writer) + vector_search N회 → 요약 미포함이면 가정 성립")
    print(f"   벽시계 = {elapsed_total:.1f}s ({elapsed_total/60:.1f}분) / 30분 판정선")

    out_path = Path(args.output) if args.output else (
        root / "scripts" / "output" / "§research-1" / f"R3a_run_{int(t_start)}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "topic_slug": TOPIC_SLUG, "elapsed_s": round(elapsed_total, 1),
        "final_path": final_path, "missing_titles": missing,
        "sections": rows, "usage_main_thread": u, "summarized_count": summarized,
        "shadow_refs_docs": len(shadow.get("docs") or []),
        "stuck_summary_threads": stuck,
        "summary_join_timeout": summary_join_timeout,   # P-2 — true 면 요약 콜 수는 절단값
        "summarized_is_complete": (not summary_join_timeout),
        "d3_samples": samples,
        "log_path": str(log_path),
        "p5_smoke_set_variants": len({tuple(r["probe"]["p3_smoke_lines"]) for r in rows}),
        "preflight": {k: v for k, v in pre.items() if k != "titles"},
        "verdict": {"missing_zero": ok_missing, "marker_ok": ok_marker, "unseen_zero": not unseen},
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n   결과 JSON → {out_path}")

    if not ok_marker:
        print("\n🛑 [C7-a] D4 항목 2 미달 — 이것은 **실측 결과지 드라이버 결함이 아니다.**")
        print("   RAG_TOP_K 등 조건을 바꾸지 말 것(§7 하류 봉합 금지). 보고하고 STOP.")
    return 0 if (ok_missing and ok_marker and not unseen) else 1


if __name__ == "__main__":
    raise SystemExit(main())
