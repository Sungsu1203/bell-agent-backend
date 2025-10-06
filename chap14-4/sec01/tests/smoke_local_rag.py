# tests/smoke_local_rag.py
import os, sys, time, json
from pathlib import Path

# 0) 디버그: 현재 작업 디렉터리 / 파일 존재 확인
print("[DEBUG] CWD =", os.getcwd(), flush=True)
print("[DEBUG] __file__ =", __file__, flush=True)

# 1) 프로젝트 루트(= tests의 상위) 를 sys.path에 추가
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print("[DEBUG] ROOT added to sys.path:", ROOT, flush=True)

# 2) 임포트 테스트 (에러 나면 여기서 바로 보입니다)
from tools.local_rag import ingest_local_files
from tools.web_rag import add_web_pages_json_to_chroma, web_page_json_to_documents

print("[DEBUG] imports OK", flush=True)

# 3) 임시 테스트 폴더/파일 만들기
TMP = Path("D:/tmp/rag_smoke").resolve()
(TMP / "sub").mkdir(parents=True, exist_ok=True)
(TMP / "a.txt").write_text("hello v1", encoding="utf-8")
(TMP / "sub" / "b.md").write_text("# note v1\nline", encoding="utf-8")
print("[DEBUG] test files created under:", TMP, flush=True)

# 4) 격리된 RAG 저장소 환경 설정
os.environ["CHROMA_NAMESPACE"] = "smoke_local"
os.environ["CHROMA_DIR"] = str(TMP / "chroma_store")

# os.environ["LOCAL_RAG_VERSION_MODE"] = "sha1"  # 필요시 켜기

globs = [str(TMP / "**/*.txt"), str(TMP / "**/*.md"), str(TMP / "**/*.pdf") ]

def run_once(tag: str):
    print(f"\n=== {tag} ===", flush=True)
    jsons, docs_preview, chunks = ingest_local_files(
        globs=globs,
        namespace=os.environ["CHROMA_NAMESPACE"],
        persist_directory=os.environ["CHROMA_DIR"],
        topic_slug="smoke",
        root_dir=str(ROOT),
        add_web_pages_json_to_chroma=add_web_pages_json_to_chroma,
        web_page_json_to_documents=web_page_json_to_documents,
    )
    print(f"\n[{tag}] jsons={jsons} chunks={chunks} preview={len(docs_preview)}")
    # source에 버전 접미사(__v_... / __p_...__v_...)가 실제 들어갔는지 확인
    if jsons:
        items = json.load(open(jsons[-1], "r", encoding="utf-8"))
        for it in items[:3]:
            print(" sample source:", it.get("source"))

# 1) 최초 인덱싱 -> chunks > 0 이어야 정상
run_once("run1")

# 2) 동일 실행(변경 없음) -> "No new urls to process"로 인해 chunks == 0 이어야 정상
run_once("run2")

# 3) 파일 변경 → mtime/sha1 버전이 달라져야 chunks > 0
time.sleep(1)  # mtime 단위 충돌 방지
(TMP / "a.txt").write_text("hello v2", encoding="utf-8")
run_once("run3")

# 4) 강제 리인덱싱(내용 변화 없이도) → LOCAL_RAG_FORCE_VERSION로 강제 버전
os.environ["LOCAL_RAG_FORCE_VERSION"] = "force_001"
run_once("run4")

print("\n[DEBUG] Done.", flush=True)
