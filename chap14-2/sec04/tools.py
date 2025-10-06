import os
from pathlib import Path
from tavily import TavilyClient
from langchain_core.tools import tool
from langchain_community.document_loaders import WebBaseLoader
from typing import Sequence, Optional, Tuple
from collections import defaultdict
import hashlib
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from datetime import datetime
import json

from dotenv import load_dotenv, find_dotenv

dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, override=False)
else:
    print("[INFO] .env 미발견: OS 환경변수만 사용합니다.")

absolute_path = os.path.abspath(__file__) # 현재 파일의 절대 경로 반환
current_path = os.path.dirname(absolute_path) # 현재 .py 파일이 있는 폴더 경로

# from dotenv import load_dotenv
# load_dotenv(r"D:\GPT_AGENT_2025_BOOK\chap02\.env")

api_key=os.getenv("OPENAI_API_KEY")

# RAG를 위한 설정
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

# 오픈AI Embedding 설정
embedding = OpenAIEmbeddings(model='text-embedding-3-large')

# ──────────────────────────────────────────────
# VectorStore 캐시: (persist_dir, collection)별로 재사용
# ──────────────────────────────────────────────
_VS_CACHE: dict[tuple[str, str], Chroma] = {}

def _default_chroma_dir(namespace: str) -> str:
    # env 우선, 없으면 ./data/chroma_store/<namespace>
    base = os.getenv("CHROMA_DIR")
    if base:
        return base
    return str(Path(__file__).resolve().parent / "data" / "chroma_store" / namespace)

def _get_embeddings(embedding=None):
    return embedding or OpenAIEmbeddings(model="text-embedding-3-large")

def _get_vs(collection_name: str, persist_directory: str, embedding=None) -> Chroma:
    key = (persist_directory, collection_name)
    vs = _VS_CACHE.get(key)
    if vs is None:
        vs = Chroma(
            collection_name=collection_name,
            persist_directory=persist_directory,
            embedding_function=_get_embeddings(embedding),
        )
        _VS_CACHE[key] = vs
    return vs

@tool
def web_search(query: str):
    """
    주어진 query에 대해 웹검색을 하고, 결과를 반환한다.
    반환: (results(list[dict]), resources_json_path(str))
    """
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

    resp = client.search(
        query, 
        search_depth="advanced",
        include_raw_content=True,
    )
    
    # dict / pydantic 모델 모두 대응
    if isinstance(resp, dict):
        results = resp.get("results", []) or []

    else:
        # Tavily가 모델로 돌려줄 경우
        try:
            results = []
            for r in getattr(resp, "results", []):
                if isinstance(r, dict):
                    results.append(r)
                elif hasattr(r, "model_dump"):
                    results.append(r.model_dump())
                else:
                    results.append(dict(r))
        except Exception:
            results = []

    # raw_content 비어있으면 loader로 보강
    for r in results:
        rc = r.get("raw_content")
        if not rc:
            try:
                r["raw_content"] = load_web_page(r["url"])
            except Exception:
                r["raw_content"] = r.get("content", "")

    resources_json_path = os.path.join(
        current_path,
        "data",
        f"resources_{datetime.now().strftime('%Y_%m%d_%H%M%S')}.json",
    )
    with open(resources_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results, resources_json_path

def web_page_to_document(web_page):
    # raw_content와 content 중 정보가 많은 것을 page_content로 한다.
    if len(web_page['raw_content']) > len(web_page['content']):
        page_content = web_page['raw_content']
    else:
        page_content = web_page['content']
    # 랭체인 Document로 변환
    document = Document(
        page_content=page_content,
        metadata={
            'title': web_page['title'],
            'source': web_page['url']
        }
    )

    return document


def web_page_json_to_documents(json_file):
    with open(json_file, "r", encoding='utf-8') as f:
        resources = json.load(f)

    documents = []

    for web_page in resources:
        document = web_page_to_document(web_page)
        documents.append(document)

    return documents


def split_documents(documents, chunk_size=1000, chunk_overlap=100):
    print('Splitting documents...')
    print(f"{len(documents)}개의 문서를 {chunk_size}자 크기로 중첩 {chunk_overlap}자로 분할합니다.\n")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )

    splits = text_splitter.split_documents(documents)

    print(f"총 {len(splits)}개의 문서로 분할되었습니다.")
    return splits

# documents를 chroma DB에 저장하는 함수
def documents_to_chroma(
    documents: Sequence[Document],
    *,
    chunk_size: int=1000,
    chunk_overlap: int=100,
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
    persist_directory: Optional[str] = None,
    embedding=None,
    # 선택: 컬렉션 비우고 새로 시작하고 싶을 때
    clear: bool = False,
    # 선택: URL 중복방지 로그 출력
    verbose: bool = True,
    ) -> Tuple[int,int]:
    """
    문서들을 세션/주제별 Chroma 컬렉션에 적재한다.
    - namespace/collection_name + persist_directory 로 논리/물리 격리
    - 기존에 저장된 URL(source) 은 **건너뛰어** 중복 적재 방지
    - 반환: (원본 문서 수, 적재된 청크 수)
    """
    # print("Documents를 Chroma DB에 저장합니다.")

    # 0) 네임스페이스/디렉터리 결정
    ns = collection_name or namespace or os.getenv("CHROMA_NAMESPACE", "default")
    pd = persist_directory or os.getenv("CHROMA_DIR") or _default_chroma_dir(ns)
    os.makedirs(pd, exist_ok=True)

    # 1) 필요 시 컬렉션 초기화(옵션)
    if clear:
        _VS_CACHE.pop((pd, ns), None)
        try:
            if os.path.isdir(pd):
                import shutil
                shutil.rmtree(pd)
            os.makedirs(pd, exist_ok=True)
        except Exception:
            pass

    # 2) 벡터스토어 준비
    vs = _get_vs(ns, pd, embedding)

    # 3) 기존에 저장된 URL 집합 구하기
    #    (가급적 where $in 필터 사용 → 불가하면 전체 메타데이터 스캔으로 폴백)
    all_urls = {
        (getattr(d, "metadata", {}) or {}).get("source")
        for d in (documents or [])
        if (getattr(d, "metadata", {}) or {}).get("source")
    }
    stored_urls = set()
    if all_urls:
        try:
            # 최신 chromadb는 $in 필터 지원
            res = vs._collection.get(
                where={"source": {"$in": list(all_urls)}},
                include=["metadatas"],
            )
            metas = (res or {}).get("metadatas") or []
            for m in metas:
                if isinstance(m, dict) and m.get("source"):
                    stored_urls.add(m["source"])
        except Exception:
            # 폴백: 전체 메타데이터 스캔(규모가 크면 비용 큼)
            try:
                res = vs._collection.get(include=["metadatas"])
                metas = (res or {}).get("metadatas") or []
                for m in metas:
                    if isinstance(m, dict) and m.get("source"):
                        stored_urls.add(m["source"])
            except Exception:
                stored_urls = set()

    # 4) 새로운 문서만 선별
    new_documents: list[Document] = []
    new_url_set = all_urls - stored_urls
    for d in (documents or []):
        src = (getattr(d, "metadata", {}) or {}).get("source")
        if src and src in new_url_set:
            new_documents.append(d)
            if verbose:
                print(d.metadata)

    if not new_documents:
        if verbose:
            print("[INFO] documents_to_chroma: No new urls to process")
        return (len(documents or []), 0)
    
    # 5) 청크 분할
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    splits = splitter.split_documents(new_documents)
    if not splits:
        return (len(documents or []), 0)
    
    # 6) (권장) 결정적 ID로 업서트-친화적 적재
    #    같은 URL이면 같은 ID prefix를 써서 **중복 적재 시 덮어쓰기/무시**가 일관되게 동작
    ids = []
    counter = defaultdict(int)
    for s in splits:
        src = (getattr(s, "metadata", {}) or {}).get("source", "")
        if src:
            base = hashlib.sha1(src.encode("utf-8", "ignore")).hexdigest()
            counter[base] += 1
            ids.append(f"{base}-{counter[base]:06d}")
        else:
            # source가 없는 드문 케이스는 임의 ID (중복 제어는 어려움)
            counter["__none__"] += 1
            ids.append(f"none-{counter['__none__']:06d}")

    try:
        vs.add_documents(splits, ids=ids)  # 일부 버전은 upsert 동작
    except Exception:
        # ids 지원이 불안정한 환경 폴백
        vs.add_documents(splits)

     # ✅ 새/구버전 호환: persist() 있으면 호출, 없으면 무시
    try:
        vs.persist()
    except AttributeError:
        pass
    return (len(documents or []), len(splits))

# json 파일에서 documents를 만들고, 그 documents들을 Chroma DB에 저장
def add_web_pages_json_to_chroma(
    json_file,
    chunk_size=1000,
    chunk_overlap=100,
    # 새 인자들(옵션)
    namespace: str | None = None,              # Pinecone의 namespace 개념. Chroma에선 collection_name으로 매핑
    collection_name: str | None = None,        # 직접 지정하고 싶을 때
    persist_directory: str | None = None,      # 세션/주제별 폴더
    embedding=None,                             # 맞춤 임베딩(없으면 OpenAIEmbeddings)
    clear: bool = False,
    ) -> Tuple[int, int]:
    """
    웹 페이지 JSON을 문서로 변환 후, 세션/주제별 컬렉션에 적재.
    반환: (원본 문서 수, 적재된 청크 수)
    웹 페이지 JSON을 읽어 세션/주제별 Chroma 컬렉션에 적재.
    인자 미지정 시, 환경변수로 보완:
      - CHROMA_NAMESPACE → collection_name (기본: 'default')
      - CHROMA_DIR       → persist_directory (기본: ./data/chroma_store/<namespace>)
    """
    documents = web_page_json_to_documents(json_file)
    return documents_to_chroma(
        documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        namespace=namespace,
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding=(embedding or OpenAIEmbeddings(model="text-embedding-3-large")),
        clear=clear,
    )

def load_web_page(url: str):
    loader = WebBaseLoader(url, verify_ssl=False)

    content = loader.load()
    raw_content = content[0].page_content.strip()   #①

    while '\n\n\n' in raw_content or '\t\t\t' in raw_content:
        raw_content = raw_content.replace('\n\n\n', '\n\n')
        raw_content = raw_content.replace('\t\t\t', '\t\t')
        
    return raw_content

@tool
def retrieve(
    query: str, 
    top_k: int=5,
    # 새 인자들(옵션)
    namespace: str | None = None,
    collection_name: str | None = None,
    persist_directory: str | None = None,
    embedding=None,
    ):
    """
    세션/주제별 컬렉션에서 질의.
    미지정 시 CHROMA_NAMESPACE/CHROMA_DIR 사용.
    전역 vectorstore가 있더라도, 네임스페이스가 지정되면 우선한다.
    """
    ns = collection_name or namespace or os.getenv("CHROMA_NAMESPACE", "default")
    pd = persist_directory or os.getenv("CHROMA_DIR") or _default_chroma_dir(ns)

    vs = _get_vs(ns, pd, embedding)
    retriever = vs.as_retriever(search_kwargs={"k": top_k})
    
    return retriever.invoke(query)

# ==== Chapter Writing Helpers (for chapter_writer) ====
import re

CHAPTER_DIR = Path(current_path) / "chapters"
CHAPTER_DIR.mkdir(exist_ok=True)  # "chapters" 폴더 없으면 자동 생성

def slugify(text: str) -> str:
    """제목을 파일 이름으로 바꿔주는 함수 (띄어쓰기/특수문자 정리)"""
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s\-]+", "-", text)
    return text or "untitled"

def parse_outline_headings(outline_text: str) -> list[tuple[int, str]]:
    """아웃라인(목차)에서 #, ##, ###로 시작하는 줄을 (레벨, 제목)으로 뽑아냄"""
    items: list[tuple[int, str]] = []
    for line in outline_text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if m:
            level = len(m.group(1))   # #은 1, ##은 2, ###은 3...
            title = m.group(2).strip()
            items.append((level, title))
    return items

def chapter_filepath(title: str) -> Path:
    """제목을 chapters/ 폴더 내 Markdown 경로로 변환"""
    return CHAPTER_DIR / f"{slugify(title)}.md"

# DOC_MODE-aware replacements
def _mode_value() -> str:
    return (os.getenv("DOC_MODE", "book") or "book").strip('"').lower()

def _path_for_title(title: str, mode: str | None = None) -> str:
    """
    DOC_MODE에 맞춰 sections/ 또는 chapters/ 경로로 변환해 파일 경로 문자열 반환
    """
    m = (mode or _mode_value())
    if m == "report":
        return str(get_content_dir("report") / f"{section_slugify(title)}.md")
    # default: book
    return str(chapter_filepath(title))

def next_unwritten_title(outline_text: str, mode: str | None = None) -> str | None:
    """
    아직 작성되지 않은 목차 제목을 자동 선택 (DOC_MODE 인지)
    우선순위: ## 레벨 먼저 → 없으면 # 레벨
    """
    m = (mode or _mode_value())
    headings = parse_outline_headings(outline_text)

    # 1차: ## 이상
    for level, title in headings:
        if level >= 2:
            path = _path_for_title(title, m)
            if not os.path.exists(path):
                return title

    # 2차: # 레벨
    for level, title in headings:
        if level == 1:
            path = _path_for_title(title, m)
            if not os.path.exists(path):
                return title

    return None

def is_written(title: str, mode: str | None = None) -> bool:
    return os.path.exists(_path_for_title(title, mode))

def save_chapter(title: str, content: str) -> Path:
    """본문을 Markdown 파일로 저장하고 경로 반환"""
    p = chapter_filepath(title)
    p.write_text(content, encoding="utf-8")
    return p

# ==== Report Writing Helpers (for section_writer) ====

def get_content_dir(mode: str) -> Path:
    base = Path(current_path)
    folder = "sections" if mode == "report" else "chapters"
    p = base / folder
    p.mkdir(exist_ok=True)
    return p

def section_slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s\-]+", "-", text)
    return text or "untitled"

def section_filepath(title: str, mode: str = "report") -> Path:
    return get_content_dir(mode) / f"{section_slugify(title)}.md"

def save_section(title: str, content: str, mode: str = "report") -> Path:
    p = section_filepath(title, mode)
    p.write_text(content, encoding="utf-8")
    return p


if __name__ == "__main__":
    # results, resources_json_path = web_search.invoke("2025년 한국 경제 전망")
    # print(results)

    # result = load_web_page("https://eiec.kdi.re.kr/publish/columnView.do?cidx=15029&ccode=&pp=20&pg=&sel_year=2025&sel_month=01")
    # print(result)

    # documents = web_page_json_to_documents(f'{current_path}/data/resources_2025_0305_231308.json')  
    # print(documents[-1])

    # splits = split_documents(documents)
    # print(splits)

    # add_web_pages_json_to_chroma(f'{current_path}/data/resources_2025_0305_231308.json')
    retrieved_docs = retrieve.invoke({"query": "한국 경제 위험 요소 "})
    print(retrieved_docs)