"""인덱스 임베딩 모델 검증 도구.

`data/chroma_store/`의 모든 NS를 자동 스캔하고, 각 NS의 첫 청크를
두 모델 (text-embedding-004, text-multilingual-embedding-002)로
다시 임베딩한 결과와 코사인 유사도를 비교한다. 어느 모델로
인덱싱되었는지 명확히 판정한다.

용도:
  - 임베딩 모델 마이그레이션 후 검증
  - 인덱스가 의심스러울 때 진단
  - 다음 모델 변경 시 영향 평가

판정 기준:
  - cos(stored, X) > 0.9 → 모델 X로 인덱싱됨
  - 둘 다 < 0.5 → UNKNOWN (다른 모델 사용 또는 손상)

사용:
  python tools/diagnose_embed_validate.py
"""
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# .env 자동 로드
import core.config  # noqa: F401

from google import genai

from tools.web_rag.ingest_vector import _default_chroma_dir, _get_vs


# 비교할 모델 후보 (현재 + 이전)
MODELS_TO_COMPARE = [
    ("old", "text-embedding-004"),
    ("new", "text-multilingual-embedding-002"),
]

# 판정 임계값
MATCH_THRESHOLD = 0.9
UNKNOWN_THRESHOLD = 0.5


def _cos(a: list[float], b: list[float]) -> float:
    """코사인 유사도."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _discover_namespaces(chroma_root: Path) -> list[str]:
    """`data/chroma_store/` 안의 NS 디렉토리 자동 탐색.

    Chroma가 만든 NS 디렉토리는 `chroma.sqlite3`를 포함한다.
    백업 디렉토리(`*_backup_*`) 등 다른 디렉토리는 제외.
    """
    if not chroma_root.exists():
        return []

    namespaces = []
    for child in sorted(chroma_root.iterdir()):
        if not child.is_dir():
            continue
        # backup 등 우회
        if "backup" in child.name.lower():
            continue
        # chroma.sqlite3가 있어야 진짜 NS
        if not (child / "chroma.sqlite3").exists():
            continue
        namespaces.append(child.name)
    return namespaces


def _judge(cos_old: float, cos_new: float) -> str:
    """판정 결과 문자열."""
    if cos_new > MATCH_THRESHOLD and cos_old < UNKNOWN_THRESHOLD:
        return "✅ SUCCESS (new model)"
    if cos_old > MATCH_THRESHOLD and cos_new < UNKNOWN_THRESHOLD:
        return "❌ FAIL (still old model)"
    if cos_old > MATCH_THRESHOLD and cos_new > MATCH_THRESHOLD:
        return "? AMBIGUOUS (both models match — unexpected)"
    return "? UNKNOWN (no model matches)"


def _check_namespace(client: genai.Client, ns: str) -> dict:
    """단일 NS 검증."""
    pd = _default_chroma_dir(ns)
    result: dict = {"ns": ns, "ok": False}

    try:
        vs = _get_vs(ns, pd)
        col = vs._collection
        n = col.count()
    except Exception as e:
        result["error"] = f"open failed: {e}"
        return result

    result["chunk_count"] = n
    if n == 0:
        result["empty"] = True
        return result

    try:
        retrieved = col.get(limit=1, include=["embeddings", "documents"])
        embs = retrieved.get("embeddings")
        docs = retrieved.get("documents") or []
        if embs is None or len(embs) == 0:
            result["error"] = "no embeddings retrieved"
            return result
        stored = [float(x) for x in embs[0]]
        text = docs[0] if docs else ""
    except Exception as e:
        result["error"] = f"retrieve failed: {e}"
        return result

    result["sample_text"] = text[:80]

    # 두 모델로 다시 임베딩
    cos_results = {}
    for label, model in MODELS_TO_COMPARE:
        try:
            r = client.models.embed_content(model=model, contents=text)
            if not r.embeddings:
                cos_results[label] = None
                continue
            v = r.embeddings[0].values
            if v is None:
                cos_results[label] = None
                continue
            cos_results[label] = _cos(stored, list(v))
        except Exception as e:
            cos_results[label] = f"error: {e}"

    result["cos"] = cos_results
    result["ok"] = True
    result["verdict"] = _judge(
        cos_results.get("old", 0.0) if isinstance(cos_results.get("old"), float) else 0.0,
        cos_results.get("new", 0.0) if isinstance(cos_results.get("new"), float) else 0.0,
    )
    return result


def main() -> int:
    chroma_root = ROOT / "data" / "chroma_store"
    namespaces = _discover_namespaces(chroma_root)
    if not namespaces:
        print(f"No namespaces found in {chroma_root}")
        return 1

    print(f"Found {len(namespaces)} namespace(s) in {chroma_root}")
    print()

    project = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_REGION", "us-central1")
    if not project:
        print("ERROR: GCP_PROJECT_ID not set. .env 로드 실패.")
        return 1

    client = genai.Client(vertexai=True, project=project, location=location)

    summary: list[tuple[str, str]] = []
    for ns in namespaces:
        print(f"=== {ns} ===")
        r = _check_namespace(client, ns)

        if "error" in r:
            print(f"  ERROR: {r['error']}")
            summary.append((ns, "ERROR"))
            print()
            continue

        if r.get("empty"):
            print(f"  chunk count: 0 (empty)")
            summary.append((ns, "EMPTY"))
            print()
            continue

        print(f"  chunk count: {r['chunk_count']}")
        print(f"  sample text: {r['sample_text']!r}")
        for label, model in MODELS_TO_COMPARE:
            cos = r["cos"].get(label)
            if cos is None:
                print(f"  cos vs {label} ({model}): N/A")
            elif isinstance(cos, float):
                print(f"  cos vs {label} ({model}): {cos:.4f}")
            else:
                print(f"  cos vs {label} ({model}): {cos}")
        print(f"  verdict: {r['verdict']}")
        summary.append((ns, r["verdict"]))
        print()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for ns, verdict in summary:
        print(f"  {ns:50s}  {verdict}")

    return 0


if __name__ == "__main__":
    sys.exit(main())