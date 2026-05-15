"""§14-2 Phase B Chroma ns_web reset 전용 subprocess (v2).

책임: venfobel-vitamin-web persist 디렉토리를 통째로 삭제 + 재생성.
shutil.rmtree 만 사용. **LangChain Chroma 절대 import 하지 않음** —
import 즉시 자신이 file lock (mmap) 잡아서 rmtree 가 PermissionError 발생.

cross-check (after count) 는 measurement subprocess 의 cross_check_chroma_count 가 담당.
새 process 라 이전 lock 영향 없음.

cleared=True 조건: persist_dir 가 존재하지 않거나 비어있음.
실패 시 errors 박제 + cleared=False.

CLI:
    python scripts/_phase_b_clear_ns.py --output <path.json>
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# .env.vertex 로드 (persist_dir 해석에 필요)
try:
    from dotenv import load_dotenv
    env_vertex = PROJECT_ROOT / ".env.vertex"
    if env_vertex.exists():
        load_dotenv(env_vertex, override=True)
except ImportError:
    pass

# §14-3 Step 3: --ns 인자로 토픽 변경 가능 (back-compat: 미지정 시 기존 hard-coded).
DEFAULT_TOPIC_SLUG = "venfobel-vitamin"
DEFAULT_NS_WEB = f"{DEFAULT_TOPIC_SLUG}-web"


def _resolve_persist_dir(ns_web: str) -> tuple[str | None, str | None]:
    """ns_web 의 persist_dir 해석. import _default_chroma_dir 만 사용 (Chroma 객체 미생성)."""
    try:
        from tools.web_rag.ingest_vector import _default_chroma_dir
        return _default_chroma_dir(ns_web), None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:200]}"


def _dir_size_files(p: Path) -> tuple[int, int]:
    """디렉토리 내 파일 개수 + 총 byte (count cross-check 의 proxy)."""
    if not p.exists():
        return 0, 0
    n, total = 0, 0
    try:
        for fp in p.rglob("*"):
            if fp.is_file():
                n += 1
                try:
                    total += fp.stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    return n, total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--ns", default=None,
                        help="대상 ns_web 이름 (default: venfobel-vitamin-web, §14-3 Step 3 추가)")
    args = parser.parse_args()

    ns_web = args.ns or DEFAULT_NS_WEB

    t0 = time.monotonic()
    result: dict = {
        "ns": ns_web,
        "persist_dir": None,
        "before_count": None,        # filesystem file count (proxy)
        "before_bytes": None,
        "after_count": None,
        "after_bytes": None,
        "method": "shutil.rmtree",
        "cleared": False,
        "fallback_used": False,
        "errors": [],
        "elapsed_sec": 0.0,
    }
    print(f"[clear] target ns={ns_web}", flush=True)

    pd_str, pd_err = _resolve_persist_dir(ns_web)
    if pd_err:
        result["errors"].append(f"persist_dir resolve: {pd_err}")
        result["elapsed_sec"] = round(time.monotonic() - t0, 2)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                                     encoding="utf-8")
        return 1
    result["persist_dir"] = pd_str
    pd = Path(pd_str)
    print(f"[clear] persist_dir={pd}", flush=True)

    # before snapshot
    n_before, b_before = _dir_size_files(pd)
    result["before_count"] = n_before
    result["before_bytes"] = b_before
    print(f"[clear] before: files={n_before}  bytes={b_before:,}", flush=True)

    # rmtree
    try:
        if pd.exists():
            shutil.rmtree(pd, ignore_errors=False)
        pd.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        # Windows file lock 발생 시 ignore_errors=True 로 재시도 (partial delete)
        result["errors"].append(f"rmtree PermissionError 1st: {str(e)[:300]}")
        time.sleep(1.0)
        try:
            shutil.rmtree(pd, ignore_errors=True)
            pd.mkdir(parents=True, exist_ok=True)
            result["fallback_used"] = True
        except Exception as e2:
            result["errors"].append(f"rmtree retry: {type(e2).__name__}: {str(e2)[:300]}")
    except Exception as e:
        result["errors"].append(f"rmtree: {type(e).__name__}: {str(e)[:300]}")

    # after snapshot
    n_after, b_after = _dir_size_files(pd)
    result["after_count"] = n_after
    result["after_bytes"] = b_after
    print(f"[clear] after:  files={n_after}  bytes={b_after:,}", flush=True)

    # cleared 판정: 디렉토리 비어있거나 (chromadb 가 빈 collection 만들 때 metadata 일부만 남는 케이스 허용)
    # 보수적으로: file count <= 3 (chromadb 의 빈 collection metadata) 이면 cleared
    result["cleared"] = (n_after <= 3)
    result["elapsed_sec"] = round(time.monotonic() - t0, 2)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                                 encoding="utf-8")
    print(f"[clear] {'OK' if result['cleared'] else 'FAILED'}  "
          f"files {n_before}→{n_after}  bytes {b_before:,}→{b_after:,}  "
          f"fallback={result['fallback_used']}  elapsed={result['elapsed_sec']}s",
          flush=True)
    return 0 if result["cleared"] else 2


if __name__ == "__main__":
    sys.exit(main())
