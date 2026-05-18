# tools/web_rag/ingest_docs.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os, io, json
from pathlib import Path
from typing import Any, List, Dict, Sequence, Optional, Iterable, Tuple, Callable
from types import ModuleType

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, unquote

from requests.exceptions import SSLError as _SSLError

import re as _re

from langchain_core.documents import Document

# 설정/공통 헬퍼
from .ingest_config import (
    CFG,
    _cfg_str,
    _cfg_bool,
    _cfg_int,
)

# 기존 utils에서 가져오던 것 (session, DATA_DIR, _clean_text 등 필요한 부분만 선택)
from .utils import (
    DATA_DIR,
    _clean_text,
    _is_block_page,
    _looks_like_pdf_bytes,
    _looks_like_serialized_blob,
    normalize_url as _normalize_url,
)


# 필요하면 pypdf2/pdfminer/pandas도 여기에서 import
_pypdf2: ModuleType | None
try:
    import PyPDF2 as _pypdf2_mod
    _pypdf2 = _pypdf2_mod
except Exception:
    _pypdf2 = None

_pdfminer_extract_text: Callable[..., str] | None
try:
    from pdfminer.high_level import extract_text as _pdfminer_extract_text_mod
    _pdfminer_extract_text = _pdfminer_extract_text_mod
except Exception:
    _pdfminer_extract_text = None

try:
    import pandas as _pd  # type: ignore[import-untyped]
except Exception:
    _pd = None


# ─────────────────────────────────────────────────────────────
# bytes → text 디코딩 / PDF / HTML 유틸
# ─────────────────────────────────────────────────────────────

def _decode_bytes(data: bytes, encoding_hint: str | None = None) -> str:
    """
    HTTP 응답 바이트를 텍스트로 디코딩한다.
    - encoding_hint 우선
    - 실패 시 chardet를 사용해 추론
    - 그래도 안 되면 'utf-8', 'cp949' 순서로 폴백
    """
    if not data:
        return ""

    enc_candidates: list[str] = []
    if encoding_hint:
        enc_candidates.append(encoding_hint)

    # chardet에 의존할 수 있으면 사용
    try:
        import chardet

        det = chardet.detect(data)
        if det.get("encoding"):
            enc_candidates.append(str(det["encoding"]))
    except Exception:
        pass

    enc_candidates.extend(["utf-8", "cp949"])

    for enc in enc_candidates:
        try:
            return data.decode(enc, errors="replace")
        except Exception:
            continue
    # 마지막 폴백
    return data.decode("utf-8", errors="replace")


def _pdf_bytes_to_text(data: bytes, url: str = "") -> str:
    """PDF bytes → 텍스트 추출 (PyPDF2 → pdfminer 순 폴백)."""
    if not data:
        return ""

    # ENV 기반 제한값 읽기 (없으면 기본값)
    _max_pages = _cfg_int("WEB_PDF_MAX_PAGES", 5)
    _max_chars = _cfg_int("WEB_PDF_MAX_CHARS", 10000)

    if _pypdf2 is not None:
        try:
            reader = _pypdf2.PdfReader(io.BytesIO(data))
            total_pages = len(reader.pages)
            texts: list[str] = []
            char_count = 0
            for i, page in enumerate(reader.pages):
                # 페이지 수 제한
                if i >= _max_pages:
                    logger.debug("[pdf] page limit reached (%d/%d): %s", i, total_pages, url)
                    break
                try:
                    t = page.extract_text() or ""
                    if t:
                        texts.append(t)
                        char_count += len(t)
                        # 글자 수 제한
                        if char_count >= _max_chars:
                            logger.debug("[pdf] char limit reached (%d chars): %s", char_count, url)
                            break
                except Exception:
                    continue
            if texts:
                result = "\n\n".join(texts)
                return result[:_max_chars]  # 최종 글자 수 상한
        except Exception:
            logger.debug("PyPDF2 parsing failed for %s", url, exc_info=True)

    if _pdfminer_extract_text is not None:
        try:
            text = _pdfminer_extract_text(io.BytesIO(data)) or ""
            return text[:_max_chars]  # pdfminer도 글자 수 상한 적용
        except Exception:
            logger.debug("pdfminer parsing failed for %s", url, exc_info=True)

    return ""


def _load_html_as_text(html: str, url: str = "") -> str:
    """
    HTML → 본문 텍스트 추출.
    여기서는 우선 간단히 _clean_text만 사용하고,
    필요시 BeautifulSoup 기반 정제 로직을 단계적으로 이관한다.

    ※ 주의: 이 함수는 "HTML 문자열"을 인자로 받는 헬퍼입니다.
    URL 기반 로딩은 web_results_to_documents 쪽에서
    ingest._load_html_as_text 또는 ingest_net.fetch_text와 조합해서 처리합니다.
    """
    text = _clean_text(html)
    return text

# ─────────────────────────────────────────────────────────────
# XLSX 메타 도큐먼트 생성 (요약용)
# ─────────────────────────────────────────────────────────────

def _xlsx_sheet_summaries(xlsx_path: Path, max_rows: int = 200) -> list[dict[str, Any]]:
    """
    XLSX의 각 시트에서 상단 일부 행만 요약해서 구조화 데이터로 반환한다.
    pandas가 없으면 빈 리스트를 반환.
    """
    if _pd is None:
        return []
    try:
        summaries: list[dict[str, Any]] = []
        with _pd.ExcelFile(xlsx_path) as xls:
            for sheet_name in xls.sheet_names:
                try:
                    df = _pd.read_excel(xls, sheet_name=sheet_name, nrows=max_rows)
                except Exception:
                    continue
                summaries.append(
                    {
                        "sheet": sheet_name,
                        "rows": len(df),
                        "cols": list(map(str, df.columns)),
                    }
                )
        return summaries
    except Exception:
        logger.debug("Failed to summarize xlsx %s", xlsx_path, exc_info=True)
        return []


def _build_xlsx_meta_documents(xlsx_path: Path, url: str) -> list[Document]:
    """
    XLSX 파일에 대한 간단한 메타 도큐먼트 목록을 생성한다.
    실제 셀 내용까지 RAG에 넣기에는 부담스러울 때,
    시트 구조/컬럼명 정도만 인덱싱할 때 사용.
    """
    summaries = _xlsx_sheet_summaries(xlsx_path)
    if not summaries:
        return []
    text_lines: list[str] = [f"XLSX file summary: {xlsx_path.name}"]
    for s in summaries:
        text_lines.append(
            f"- Sheet={s.get('sheet')} rows={s.get('rows')} cols={', '.join(s.get('cols') or [])}"
        )
    text = "\n".join(text_lines)
    meta: Dict[str, Any] = {
        "source": "xlsx",
        "url": url,
        "path": str(xlsx_path),
    }
    return [Document(page_content=text, metadata=meta)]

# PDF/HTML 로더 유틸
from .utils import looks_like_pdf_url as _looks_like_pdf_url

def _call_maybe_tool(obj: Any, *args: Any, **kwargs: Any) -> Any:
    """
    LangChain Tool/Proxy/일반 함수 호출을 모두 흡수.
    우선순위: invoke() -> run() -> (callable이면 직접 호출)
    """
    inv = getattr(obj, "invoke", None)
    if callable(inv):
        return inv(*args, **kwargs)
    run = getattr(obj, "run", None)
    if callable(run):
        return run(*args, **kwargs)
    if callable(obj):
        return obj(*args, **kwargs)
    raise TypeError(f"Object is not callable and has no invoke/run: {type(obj)!r}")


# ─────────────────────────────────────────────────────────────
# web.json / search results → Documents
# ─────────────────────────────────────────────────────────────

def _promote_item_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    # §14-9 Phase 3 — vertex grounding 의 item["metadata"] (backend / alt_urls /
    # chunk_domain) 을 Document.metadata 로 promote. Chroma 가 list/dict 를 거부
    # 하므로 alt_urls 는 comma-joined str 로 flatten. 부재 키는 미포함.
    extra: Dict[str, Any] = {}
    meta = item.get("metadata")
    if not isinstance(meta, dict):
        return extra
    bk = meta.get("backend")
    if isinstance(bk, str) and bk.strip():
        extra["backend"] = bk.strip()
    cd = meta.get("chunk_domain")
    if isinstance(cd, str) and cd.strip():
        extra["chunk_domain"] = cd.strip()
    au = meta.get("alt_urls")
    if isinstance(au, (list, tuple)):
        joined = ",".join(str(u).strip() for u in au if str(u).strip())
        if joined:
            extra["alt_urls"] = joined
    elif isinstance(au, str) and au.strip():
        extra["alt_urls"] = au.strip()
    return extra


def web_results_to_documents(results: Sequence[Dict[str, Any]]) -> List[Document]:
    """
    web.json 항목(또는 검색 결과 dict 리스트)을 LangChain Document 리스트로 변환.
    - file:// 은 네트워크 요청 없이 item.content 사용
    - raw_content(HTML)가 있으면 패스 1로 처리
    - PDF 스멜나면 PDF 바이트 로더 우선, 실패시 HTML 폴백
    """
    # NOTE:
    #  - ingest.py 와의 순환 import를 피하기 위해,
    #    네트워크/정규화 유틸은 모듈 단위로 지연 import 해서 사용한다.
    _ingest_mod: ModuleType | None
    try:
        import tools.web_rag.ingest as _ingest_mod
    except Exception:  # pragma: no cover - fallback (ingest 미초기화 등)
        _ingest_mod = None

    docs: List[Document] = []
    # 정규화 후 중복 차단(같은 URL, 같은 파일 단위)
    _seen_urls: set[str] = set()
    _seen_files: set[str] = set()

    def _guess_content_type_from_path(path: str, default: str = "text/plain") -> str:
        ext = Path(path).suffix.lower()
        if ext == ".pdf": return "application/pdf"
        if ext in (".html", ".htm"): return "text/html"
        if ext == ".pptx": return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if ext == ".xlsx": return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if ext == ".docx": return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if ext in (".txt", ".md", ".markdown"): return "text/plain"
        return default

    for item in results or []:
        url: str = (item.get("source") or item.get("url") or "").strip()
        title: str = (item.get("title") or "").strip()
        item_content: str = (item.get("content") or "").strip()
        raw_content: str = (item.get("raw_content") or "").strip()

        if not url:
            if item_content:
                docs.append(Document(
                    page_content=item_content,
                    metadata={"source": "", "title": title or "(local)", "content_type": "text/plain", **_promote_item_metadata(item)}
                ))
            continue

        try:
            # ✅ 처리 전 정규화 및 fragment 제거
            if _ingest_mod is not None:
                url = _ingest_mod._normalize_before_request(url)
                # 🔧 KHIDI /fileDownload 예외 처리:
                #   - 정규화 과정에서 'www.'가 제거되면
                #     KHIDI 서버가 잘못된 Location 헤더를 돌려줘
                #     'www.khidi.or.krfiledownload' 같은 호스트로 깨질 수 있음.
                #   - /fileDownload 요청에 대해서는 항상 www 호스트를 유지/복원한다.
                try:
                    pu = urlparse(url)
                    host = (pu.netloc or "").lower()
                    path_l = (pu.path or "").lower()
                    if ("khidi.or.kr" in host) and ("filedownload" in path_l):
                        new_netloc = "www.khidi.or.kr"
                        url = urlunparse((
                            pu.scheme or "https",
                            new_netloc,
                            pu.path,
                            pu.params,
                            pu.query,
                            pu.fragment,
                        ))
                except Exception:
                    # KHIDI 보정 중 오류가 나더라도 전체 흐름을 막지 않음
                    pass

                # [C] 잡음 URL은 조기 드랍
                if url and _ingest_mod._is_noise_url(url):
                    logger.debug("[ingest][drop-noise] %s", url)
                    continue

            # 정규화된 URL 중복 차단
            if url and url in _seen_urls:
                continue
            if url:
                _seen_urls.add(url)

            parsed = urlparse(url)
            scheme = (parsed.scheme or "").lower()
            url_no_frag = url  # 이미 fragment 제거됨

            # (선택) 같은 PDF/PPTX 파일의 다중 파트 유입 차단
            if parsed.path:
                lp = parsed.path.lower()
                if lp.endswith(".pdf") or lp.endswith(".pptx"):
                    # fragment가 있으면 local_rag 청크 → 청크별 고유 URL 사용
                    if parsed.fragment:
                        dedup_key = url
                    else:
                        if _ingest_mod is not None:
                            dedup_key = _ingest_mod._base_file_key(url_no_frag)
                        else:
                            dedup_key = url_no_frag
                    if dedup_key in _seen_files:
                        continue
                    _seen_files.add(dedup_key)

            # 1) file:// — content만 사용
            if scheme == "file":
                if not item_content:
                    logger.debug("file:// url but empty content; skip: %s", url)
                    continue
                file_path = unquote(parsed.path or "")
                ctype = _guess_content_type_from_path(file_path, default="text/plain")
                docs.append(Document(
                    page_content=item_content,
                    metadata={
                        "source": url,
                        "title": title or (Path(file_path).name if file_path else "Local File"),
                        "content_type": ctype,
                        **_promote_item_metadata(item),
                    },
                ))
                continue

            # 2) raw_content 우선 (보통 HTML)
            if raw_content:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(raw_content, "lxml")
                    for tag in soup(["script", "style", "noscript"]):
                        tag.decompose()
                    text = soup.get_text(separator="\n")
                    text = _re.sub(r"[ \t]+", " ", text)
                    text = _re.sub(r"\n{3,}", "\n\n", text).strip()
                except Exception:
                    text = _re.sub(r"<[^>]+>", " ", raw_content)
                    text = _re.sub(r"\s{2,}", " ", text).strip()

                if text:
                    docs.append(Document(
                        page_content=text,
                        metadata={"source": url, "title": title or "Web", "content_type": "text/html", **_promote_item_metadata(item)},
                    ))
                    continue

            # 3) PDF 의심 → PDF 파서 우선(내부: PyPDF2 → pdfminer 폴백) + 0자 방지 가드
            if _looks_like_pdf_url(url_no_frag) and _ingest_mod is not None:
                try:
                    # ingest._fetch_binary 의 계약:
                    #   (url: str, timeout: int = 10) -> bytes | None
                    pdf_bytes: bytes | None = _ingest_mod._fetch_binary(url_no_frag)
                    if not pdf_bytes:
                        logger.warning(
                            "[ingest][pdf] no bytes fetched (None/empty); dropping url=%s",
                            url_no_frag,
                        )
                        # HTML 폴백은 하지 않고 조용히 드랍
                        continue

                    pdf_text = _pdf_bytes_to_text(pdf_bytes, url_no_frag)
                    if pdf_text and len(pdf_text.strip()) >= 30:
                        docs.append(
                            Document(
                                page_content=str(pdf_text),
                                metadata={
                                    "source": url,
                                    "title": title or "PDF",
                                    "content_type": "application/pdf",
                                    **_promote_item_metadata(item),
                                },
                            )
                        )
                        continue
                    # 최종 가드: 0자 또는 과소 텍스트면 드랍(HTML 폴백하지 않음)
                    logger.warning(
                        "[ingest][pdf] empty/too-short text after parse; dropping url=%s",
                        url_no_frag,
                    )
                    continue
                except _ingest_mod._PdfSslError:
                    # ingest 쪽 SSL 예외 → 재시도 후보 태깅
                    try:
                        _ingest_mod._record_retry_candidate(url_no_frag, reason="ssl_error")
                    except Exception:
                        logger.debug(
                            "[ingest_docs] retry-candidate tagging failed: %s",
                            url_no_frag,
                        )
                    logger.warning(
                        "[INGEST][SSL] ssl_error tagged & skipped PDF parse → fallback to HTML: %s",
                        url_no_frag,
                    )
                except Exception as e:
                    msg = str(e)
                    # DNS 해석 실패 계열은 폴백/재시도 없이 즉시 스킵
                    if (
                        "NameResolutionError" in msg
                        or "Failed to resolve" in msg
                        or "Temporary failure in name resolution" in msg
                    ):
                        logger.warning("[web_rag] DNS failure; skip (no fallback): %s", e)
                        continue
                    logger.debug("[web_rag] PDF parse failed; fallback to HTML: %s", e)

            # 4) HTML 로더
            html_text: str = ""

            # 4-1) 가능하면 ingest.py 쪽 URL 기반 HTML 로더를 우선 사용
            if _ingest_mod is not None and hasattr(_ingest_mod, "_load_html_as_text"):
                try:
                    # ingest._load_html_as_text(url: str, timeout: int = 10) 기준 호출
                    html_text = _ingest_mod._load_html_as_text(url_no_frag)
                except Exception as e:
                    logger.debug(
                        "[ingest_docs] ingest._load_html_as_text failed; fallback to local: %s",
                        e,
                    )

            # 4-2) ingest 모듈이 없거나 실패했다면, ingest_net.fetch_text + 로컬 클리너 사용
            if not html_text:
                raw_html: Optional[str] = None
                try:
                    from tools.web_rag.ingest_net import fetch_text as _fetch_text
                    raw_html = _fetch_text(url_no_frag)
                except Exception:
                    raw_html = None

                if raw_html:
                    html_text = _load_html_as_text(raw_html, url_no_frag)

            if html_text:
                docs.append(Document(
                    page_content=str(html_text),
                    metadata={"source": url, "title": title or "Web", "content_type": "text/html", **_promote_item_metadata(item)},
                ))
                continue

            # 5) 마지막 폴백: item.content
            if item_content:
                docs.append(Document(
                    page_content=item_content,
                    metadata={"source": url, "title": title or "Web", "content_type": "text/plain", **_promote_item_metadata(item)},
                ))
        except Exception as e:
            logger.warning("web_results_to_documents item fail (%s): %s", url, e)

    logger.debug("web_results_to_documents: %d docs built", len(docs))
    return docs

def web_page_json_to_documents(json_file: str) -> List[Document]:
    """web.json(배열/NDJSON/단일 dict/래핑 dict)을 유연하게 읽어 Document 리스트로 변환."""
    if not os.path.exists(json_file):
        logger.debug("web_page_json_to_documents: file not found %s", json_file)
        return []

    def _flex_load(path: str):
        txt = Path(path).read_text(encoding="utf-8")
        try:
            data = json.loads(txt)
        except json.JSONDecodeError:
            items = []
            for line in txt.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass
            return items
        # 데이터 래핑 해제
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("results", "items", "data"):
                v = data.get(k)
                if isinstance(v, list):
                    return v
            return [data]
        return []

    try:
        resources = _flex_load(json_file) or []
    except Exception as e:
        logger.warning("web_page_json_to_documents: load failed for %s: %s", json_file, e)
        resources = []

    # [B] 라운드 시작 시 호스트 실패 카운터 리셋
    #  - ingest.py 와의 순환 import를 피하기 위해 여기서 지연 import
    _ingest_mod2: ModuleType | None
    try:
        import tools.web_rag.ingest as _ingest_mod2
    except Exception:  # pragma: no cover - ingest 미초기화 등
        _ingest_mod2 = None

    def _round_fail_reset_local() -> None:
        if _ingest_mod2 is not None and hasattr(_ingest_mod2, "_round_fail_reset"):
            try:
                _ingest_mod2._round_fail_reset()
            except Exception:
                pass

    def _priority_sort_key_local(item: dict) -> tuple[int, int, int, int, str]:
        if _ingest_mod2 is not None and hasattr(_ingest_mod2, "_priority_sort_key"):
            try:
                return _ingest_mod2._priority_sort_key(item)
            except Exception:
                pass
        # fallback: 정렬 영향 최소화
        src = str(item.get("source") or item.get("url") or "")
        return (1, 1, 3, 0, src)

    _round_fail_reset_local()


    # ──────────────────────────────────────────────────────────
    # [ADD] 로컬 우선 정렬 + cap 적용
    #   - 의도: cap(1500) 이전에 findings.md > PDF > PPTX > XLSX > 기타
    #   - 기준 cap: LOCAL_RAG_MAX_DOCS (없으면 0 = 무제한)
    #   - 정렬은 전체에 적용하되, file:// 항목이 자연스럽게 상단 배치됨
    # ──────────────────────────────────────────────────────────
    try:
        if isinstance(resources, list) and resources:
            # 로컬 인제스트 가드:
            #  - file:// 항목이 1개 이상이면 로컬 정렬/캡 적용
            #  - 또는 명시적 플래그 LOCAL_PRIORITY_SORT=1
            has_file = False
            for _it in resources:
                _u = (_it.get("url") or _it.get("source") or "").strip().lower()
                if _u.startswith("file://"):
                    has_file = True
                    break
            local_sort_enabled = _cfg_bool("LOCAL_PRIORITY_SORT", True)
            if has_file or local_sort_enabled:
                before_n = len(resources)
                resources.sort(key=_priority_sort_key_local)  # in-place (ingest 기준 우선순위)
                cap = _cfg_int("LOCAL_RAG_MAX_DOCS", 0)
                if isinstance(cap, int) and cap > 0 and len(resources) > cap:
                    resources = resources[:cap]
                    logger.info(
                        "[ingest][local-priority] resources sorted & capped: %d → %d (cap=%d, file://=%s)",
                        before_n, len(resources), cap, has_file
                    )
                else:
                    logger.debug(
                        "[ingest][local-priority] resources sorted (no cap or under cap; file://=%s)",
                        has_file
                    )
            else:
                logger.debug("[ingest] skip local-priority sort/cap (no file:// and flag disabled)")
    except Exception as e:
        logger.debug("[ingest][local-priority] sort/cap skipped: %s", e)

    # 입력 단계에서도 URL 정규화 후 유일화가 적용되므로 그대로 변환
    docs = web_results_to_documents(resources)
    logger.info("web_page_json_to_documents: %d docs from %s", len(docs), json_file)
    return docs


def _is_safe_callable(obj: Any) -> bool:
    """
    multiprocessing.Manager 기반 프록시(_RootProxy 등)가
    실수로 함수처럼 호출되는 것을 방지하기 위한 헬퍼.

    - 기본적으로 callable(obj) 여야 하고,
    - 타입명이 '_RootProxy' 이거나,
    - 모듈이 'multiprocessing.managers' 인 경우는 호출하지 않는다.
    """
    if not callable(obj):
        return False
    t = type(obj)
    tname = getattr(t, "__name__", "")
    mname = getattr(t, "__module__", "")
    if tname == "_RootProxy":
        return False
    if "multiprocessing.managers" in (mname or ""):
        return False
    return True


def quick_ingest_findings(topic_slug: str) -> int:
    """
    연구 합성 결과(round-XX-findings.md)를 빠르게 web.json으로 변환하기 위한
    경량 엔트리 포인트.

    - research/<topic_slug>/round-*-findings.md 패턴을 스캔한다.
    - tools.local_rag.build_webjson_from_local을 통해
      resources/<topic_slug>/ 아래에 web.json을 생성한다.
    - Chroma 인덱싱까지는 하지 않고, “findings를 web.json 경로로 태우는 것”까지만 담당한다.
    - tools.local_rag 또는 build_webjson_from_local이 없으면 0을 반환한다.
    """
    from pathlib import Path

    try:
        # 지연 임포트로 순환 의존 최소화
        from tools.local_rag import build_webjson_from_local
    except Exception:
        logger.debug(
            "[ingest_docs] quick_ingest_findings: tools.local_rag.build_webjson_from_local not available"
        )
        return 0

    try:
        root = Path.cwd()
        research_dir = root / "research" / topic_slug
        if not research_dir.exists():
            logger.debug(
                "[ingest_docs] quick_ingest_findings: research dir not found (%s)",
                research_dir,
            )
            return 0

        pattern = "round-*-findings.md"
        findings_files = sorted(research_dir.glob(pattern))
        if not findings_files:
            logger.debug(
                "[ingest_docs] quick_ingest_findings: no findings matched (%s / %s)",
                research_dir,
                pattern,
            )
            return 0

        # web.json 저장 디렉터리: resources/<topic_slug>
        resources_dir = root / "resources" / topic_slug
        resources_dir.mkdir(parents=True, exist_ok=True)

        glob_pattern = str(research_dir / pattern)
        logger.info(
            "[ingest_docs] quick_ingest_findings: building web.json from %s → %s",
            glob_pattern,
            resources_dir,
        )

        # build_webjson_from_local(globs: list[str], out_dir: str) -> str (web.json 경로)
        out_json = build_webjson_from_local([glob_pattern], str(resources_dir))

        # 반환값이 경로이면 존재 여부 정도만 체크 (실패해도 플로우는 유지)
        try:
            out_path = Path(out_json)
            if out_path.exists():
                logger.info(
                    "[ingest_docs] quick_ingest_findings: web.json saved → %s",
                    out_path,
                )
        except Exception:
            # 반환 형식이 달라도 전체 연구 루프는 깨지지 않도록 방어
            pass

        # 몇 개의 findings 파일을 태웠는지 기준으로 count 반환
        return len(findings_files)

    except Exception as e:  # pragma: no cover - 방어적
        logger.debug("[ingest_docs] quick_ingest_findings failed: %s", e)
        return 0

__all__ = [
    # URL/정규화 유틸은 ingest.py 기준 사용 (여기서는 직접 export하지 않음)
    "_decode_bytes",
    "_pdf_bytes_to_text",
    "_load_html_as_text",
    "_xlsx_sheet_summaries",
    "_build_xlsx_meta_documents",
    "web_results_to_documents",
    "web_page_json_to_documents",
    "quick_ingest_findings",
]
