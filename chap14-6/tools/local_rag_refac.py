from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import os, re, json, glob, hashlib
from pathlib import Path
from datetime import datetime
from typing import Any, List, Tuple, Optional
from urllib.parse import unquote

from langchain_core.documents import Document

# ──────────────────────────────────────────────────────────────────────────────
# Optional dependencies: 클래스/함수 핸들을 Any로 보관(없으면 None)
# ──────────────────────────────────────────────────────────────────────────────
try:
    from bs4 import BeautifulSoup as _BeautifulSoup
    BeautifulSoup: Any = _BeautifulSoup
except Exception:
    BeautifulSoup = None
    logger.debug("BeautifulSoup not available; falling back to regex for HTML parsing.")

try:
    from pypdf import PdfReader as _PdfReader
    PdfReader: Any = _PdfReader
except Exception:
    PdfReader = None
    logger.debug("pypdf not available; PDF extraction disabled.")

try:
    import docx as _docx  # python-docx
    docx: Any = _docx
except Exception:
    docx = None
    logger.debug("python-docx not available; .docx extraction disabled.")

# 💡 [통합] unstructured 라이브러리 의존성 추가
try:
    from unstructured.partition.auto import partition
    # unstructured.documents.elements의 타입 힌트를 사용합니다.
    from unstructured.documents.elements import Table, Element
except Exception:
    partition = None
    logger.debug("unstructured library not available.")
    
# ──────────────────────────────────────────────────────────────────────────────
# 내부 유틸
# ──────────────────────────────────────────────────────────────────────────────
def _file_version(path: str) -> str:
    """
    파일 변경을 반영하는 버전 식별자. (기존 로직 유지)
    """
    forced = os.getenv("LOCAL_RAG_FORCE_VERSION")
    if forced:
        logger.debug("Using forced version for %s: %s", path, forced)
        return str(forced)

    mode = (os.getenv("LOCAL_RAG_VERSION_MODE", "mtime") or "mtime").lower()
    try:
        if mode == "sha1":
            h = hashlib.sha1()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            ver = h.hexdigest()[:12]
        else:
            st = os.stat(path)
            ver = f"{int(st.st_mtime)}_{st.st_size}"
        logger.debug("Computed version for %s: %s (mode=%s)", path, ver, mode)
        return ver
    except Exception as e:
        logger.warning("Version compute failed for %s: %s", path, e)
        return "na"


def _read_txt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def _read_md(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")

def _truthy_env(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _read_html(path: str) -> str:
    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    if BeautifulSoup is not None:
        try:
            return BeautifulSoup(raw, "lxml").get_text(" ", strip=True)
        except Exception:
            return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    txt = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", txt).strip()


def _read_docx(path: str) -> str:
    if not docx:
        raise RuntimeError("python-docx 미설치")
    d = docx.Document(path)
    return "\n".join(p.text for p in d.paragraphs)

# 💡 [통합] PPTX/XLSX 추출 함수: 모든 요소를 하나의 긴 문자열로 병합 💡
def _read_unstructured_elements(path: str) -> str:
    """unstructured를 사용하여 파일 내용을 요소별로 추출한 후, 모든 요소를 긴 문자열로 병합"""
    if not partition:
        # 설치 오류 시 runtime error 발생 (상위 try/except에서 처리됨)
        raise RuntimeError("unstructured 라이브러리 미설치") 
    
    try:
        # unstructured partition 호출
        elements = partition(filename=path)
    except Exception as e:
        logger.warning(f"Unstructured partition failed for {path}: {e}")
        return ""

    parts: List[str] = []

    for element in elements:
        content = str(element.text or "").strip()
        
        # 테이블 요소는 구조화된 텍스트(CSV/Markdown)를 추가하여 RAG가 문맥을 파악하도록 돕습니다.
        if isinstance(element, Table):
            text_as_csv = getattr(element, 'text_as_csv', '') or ""
            content = content + "\n" + text_as_csv
        
        if content:
            # 요소 간 구분을 위해 명확한 구분자 사용
            parts.append(content)
        
    # 모든 요소를 긴 문자열로 병합 (이후 RecursiveCharacterTextSplitter가 처리)
    return "\n\n---\n\n".join(parts)


# 💡 [수정된 래퍼] _read_unstructured_elements를 호출하고 반환 타입을 str로 통일
def _read_pptx(path: str) -> str: # 💡 반환 타입을 str로 명확히 수정
    return _read_unstructured_elements(path)

def _read_xlsx(path: str) -> str: # 💡 반환 타입을 str로 명확히 수정
    return _read_unstructured_elements(path)


def _read_pdf_pages(path: str) -> List[str]:
    if not PdfReader:
        raise RuntimeError("pypdf 미설치")
    reader = PdfReader(path)

    max_pages = int(os.getenv("LOCAL_RAG_PDF_MAX_PAGES", "30"))
    pages: List[str] = []
    for i, p in enumerate(reader.pages, start=1):
        if i > max_pages:
            break
        try:
            pages.append(p.extract_text() or "")
        except Exception:
            pages.append("")
    return pages


def _file_uri(path: str) -> str:
    return Path(path).resolve().as_uri()  # file:/// 형태 보장

# ──────────────────────────────────────────────────────────────────────────────
# 변환: 로컬 파일 → web.json 아이템 배열 (모든 타입 통합 처리)
# ──────────────────────────────────────────────────────────────────────────────
def _to_webjson_items(path: str) -> List[dict]:
    ext = Path(path).suffix.lower()
    title = Path(path).name
    url_click = _file_uri(path)
    ver = _file_version(path)
    
    # ... (용량 가드 로직은 그대로 유지) ...

    # -----------------------------------------------------------
    # 1. 파일 유형별 추출기 호출 및 결과 (모든 추출기는 이제 text: str을 반환)
    # -----------------------------------------------------------
    raw_content: Optional[str] = None
    items_from_reader: Optional[List[dict]] = None
    
    try:
        if ext == ".pdf":
            # PDF는 페이지별 리스트로 반환 (기존 로직 유지)
            pages = _read_pdf_pages(path)
            items_from_reader = []
            for i, txt in enumerate(pages, start=1):
                if (txt or "").strip():
                    items_from_reader.append({
                        "page_num": i,
                        "content": txt,
                    })
        
        elif ext in (".txt", ".md", ".markdown", ".html", ".htm", ".docx"):
            # 단일 텍스트 반환 추출기
            if ext in (".txt",): raw_content = _read_txt(path)
            elif ext in (".md", ".markdown"): raw_content = _read_md(path)
            elif ext in (".html", ".htm"): raw_content = _read_html(path)
            elif ext in (".docx",): raw_content = _read_docx(path)

        elif ext in (".pptx", ".xlsx"):
            # PPTX, XLSX (unstructured 기반으로 병합된 긴 문자열 반환)
            raw_content = _read_unstructured_elements(path)
        
        else:
            logger.debug("[LOCAL RAG] unsupported extension skipped: %s", path)
            return []
            
    except RuntimeError as e:
        logger.warning("[LOCAL RAG] Reader dependency failed: %s -> %s", path, e)
        return []
    except Exception as e:
        logger.warning("[LOCAL RAG] Extraction error: %s -> %s", path, e)
        # 오류 발생 시 빈 content로 처리하여 인덱싱 실패 방지 (최대한 내용만 보냄)
        if raw_content is None: raw_content = ""
        
    # -----------------------------------------------------------
    # 2. 결과 통합 및 메타데이터 생성
    # -----------------------------------------------------------
    final_items: List[dict] = []
    
    # 2-A. 리스트 형태의 결과 처리 (PDF만 해당)
    if items_from_reader is not None and isinstance(items_from_reader, list):
        for it in items_from_reader:
            # PDF 페이지 메타데이터 사용
            index_num = it.pop("page_num", 1)
            content = it.pop("content", "")
            part_label = "p" # PDF 페이지는 'p'로 고정
            
            # 컨텐츠 길이 제한 (PDF 페이지도 포함)
            max_chars = int(os.getenv("LOCAL_RAG_MAX_TEXT_CHARS", "200000"))
            if len(content) > max_chars:
                content = content[:max_chars]

            if not content.strip(): continue

            final_items.append({
                "title": f"{title} (p.{index_num})",
                "url": f"{url_click}#page={index_num}", 
                "source": f"{url_click}__p_{index_num}__v_{ver}",
                "content": content,
            })
    
    # 2-B. 단일 텍스트 형태의 결과 처리 (TXT, MD, DOCX, PPTX, XLSX)
    elif raw_content is not None:
        # PPTX, XLSX의 unstructured 결과 및 기타 단일 파일이 여기에 해당
        
        # 청크 분할은 상위 파이프라인(TextSplitter)에 맡깁니다.
        max_chars = int(os.getenv("LOCAL_RAG_MAX_TEXT_CHARS", "200000"))
        content = (raw_content or "")
        if len(content) > max_chars:
            content = content[:max_chars]
        
        if content.strip():
            final_items.append({
                "title": title,
                "url": url_click,
                "source": f"{url_click}__v_{ver}",
                "content": content, # 청크 분할이 되지 않은 긴 문자열
            })

    # -----------------------------------------------------------
    # 3. 최종 결과 반환
    # -----------------------------------------------------------
    if not final_items:
        logger.debug("[LOCAL RAG] File yielded no extractable content: %s", path)
        return []
    
    return final_items

# ──────────────────────────────────────────────────────────────────────────────
# 엔트리: globs → web.json 생성
# ──────────────────────────────────────────────────────────────────────────────
def build_webjson_from_local(globs: List[str], out_dir: str) -> str:
    # 💡 디버깅 로그 추가: CWD 및 GLOB 인자 확인
    logger.info("[LOCAL RAG] CWD: %s", os.getcwd()) 
    logger.info("[LOCAL RAG] Received globs: %s", globs)

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    files: List[str] = []

    for g in globs:
        g = os.path.expandvars(os.path.expanduser(g))
        # 💡 디버깅 로그 추가: 확장된 패턴 확인
        logger.debug("[LOCAL RAG] Expanded glob pattern: %s", g)

        # files.extend(glob.glob(g, recursive=True))
        matched = glob.glob(g, recursive=True)
        files.extend(matched)
        logger.info("[LOCAL RAG] Pattern %s matched %d files.", g, len(matched))

    files = sorted({f for f in files if os.path.isfile(f)})
    logger.info("[LOCAL RAG] Total unique files found: %d", len(files)) # 최종 파일 수 로깅
    
    items: List[dict] = []
    for f in files:
        try:
            items.extend(_to_webjson_items(f))
        except Exception as e:
            logger.warning("[LOCAL RAG] local ingest 실패: %s -> %s", f, e)

    # 빈 content 제거
    items = [it for it in items if (it.get("content") or "").strip()]

    # 디버그 요약
    uniq_sources = {it.get("source") for it in items}
    logger.info("[LOCAL RAG] files=%d items=%d unique_sources=%d", len(files), len(items), len(uniq_sources))
    if items:
        def _pretty_src(src: str) -> str:
            s = unquote(src or "")
            if "__v_" in s:
                s = s.split("__v_")[0]
            if "__p_" in s:
                s = s.split("__p_")[0]
            return s

        sample = items[:3]
        sample_titles = [it.get("title", "") for it in sample]
        sample_sources = [_pretty_src(it.get("source", "")) for it in sample]
        sample_urls = [unquote(it.get("url", "")) for it in sample]

        logger.debug("[LOCAL RAG] sample titles : %s", sample_titles)
        logger.debug("[LOCAL RAG] sample sources: %s", sample_sources)
        logger.debug("[LOCAL RAG] sample urls   : %s", sample_urls)

    ts = datetime.now().strftime("%Y_%m_%d_%H%M%S")
    out_path = os.path.join(out_dir, f"local_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(items, fp, ensure_ascii=False, indent=2)
    logger.info("[LOCAL RAG] web.json saved → %s", out_path)
    return out_path


# ──────────────────────────────────────────────────────────────────────────────
# 파이프: web.json → Chroma 적재 + 미리보기
# ──────────────────────────────────────────────────────────────────────────────
def ingest_local_files(
    globs: List[str],
    namespace: str,
    persist_directory: str | None,
    topic_slug: str,
    root_dir: str,
    add_web_pages_json_to_chroma=None,
    web_page_json_to_documents=None,
) -> Tuple[List[str], List[Document], int]:
    """
    반환: (생성 JSON 경로들, 미리보기 Documents, 인덱싱된 청크 수 합)
    """
    # ── 연구 요약(findings)을 벡터스토어에 함께 넣는 옵션 ─────────────────────
    # research/<topic-slug>/round-*-findings.md  (research_synthesizer 저장 규칙과 일치)
    if _truthy_env("INCLUDE_FINDINGS_IN_VECTOR"):
        slug = (topic_slug or os.getenv("TOPIC_SLUG") or "default").strip()
        findings_pattern = os.path.join(root_dir, "research", slug, "round-*-findings.md")
        globs = list(globs or [])
        globs.append(findings_pattern)
        logger.info("[LOCAL RAG] findings included → %s", findings_pattern)

    if not globs:
        logger.info("[LOCAL RAG] no globs provided → skip ingest")
        return ([], [], 0)

    res_dir = os.path.join(root_dir, "resources", topic_slug or "default")
    json_path = build_webjson_from_local(globs, res_dir)

    chunk_total = 0
    if add_web_pages_json_to_chroma is not None:
        try:
            _orig, chunk_count = add_web_pages_json_to_chroma(
                json_path, namespace=namespace, persist_directory=persist_directory
            )
            chunk_total += int(chunk_count or 0)
            logger.info("[LOCAL RAG] added to chroma: chunks=%s (ns=%s, dir=%s)", chunk_count, namespace, persist_directory)
        except Exception as e:
            logger.warning("[LOCAL RAG] add_web_pages_json_to_chroma(local) 실패: %s", e)

    docs_preview: List[Document] = []
    if web_page_json_to_documents is not None:
        try:
            docs_preview = web_page_json_to_documents(json_path)[:8]
            logger.debug("[LOCAL RAG] preview docs: %d", len(docs_preview))
        except Exception as e:
            logger.warning("[LOCAL RAG] preview build(local) 실패: %s", e)

    return ([json_path], docs_preview, chunk_total)
