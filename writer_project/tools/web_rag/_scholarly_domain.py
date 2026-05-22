# tools/web_rag/_scholarly_domain.py
"""§academic-4 catch 59 + catch 60-b — 학술 paper dict → 도메인 추출 layer.

4-step early-return (step_b_design.md B3 정합):
  (1) primary_location.landing_page_url (OpenAlex 전체 cover)
  (2) openAccessPdf.url (Semantic Scholar OA 한정)
  (3) DOI prefix → publisher 매핑 (catch 59 정적 table 35 entries)
  (4) venue / source.display_name 매칭 (ACADEMIC_DOMAINS 36 set 정합)

신규 prefix 발견 시 logging fallback — Step C 측정에서 unknown prefix 수집 cycle.
host normalize (www./m. 제거) — catch 60-b dedup 정합.
"""
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


# ── catch 59 정적 매핑 table (37 entries · step_b_design.md B3-2 정합) ──────
# §academic-4 Step C-1 commit 1 보강: 10.1177/ (SAGE 메인 prefix, CRITICAL) +
#                                     10.21511/ (Business Perspectives) 추가
DOI_PREFIX_TO_DOMAIN: Dict[str, str] = {
    # 광고/마케팅 핵심 publisher (10)
    "10.1016/":   "sciencedirect.com",          # Elsevier (JBR, IJRM, JR 등)
    "10.1086/":   "journals.uchicago.edu",      # Univ. of Chicago Press (JCR)
    "10.1080/":   "tandfonline.com",            # Taylor & Francis (Journal of Advertising 일부)
    "10.1207/":   "tandfonline.com",            # T&F older format
    "10.1509/":   "journals.sagepub.com",       # SAGE (Journal of Marketing 일부)
    "10.1177/":   "journals.sagepub.com",       # SAGE 메인 prefix (JoM 등, CRITICAL)
    "10.1108/":   "emerald.com",                # Emerald (Journal of Product & Brand Mgmt 등)
    "10.1287/":   "pubsonline.informs.org",     # INFORMS (Marketing Science)
    "10.5465/":   "journals.aom.org",           # Academy of Management (AMJ/AMR)
    "10.4135/":   "sk.sagepub.com",             # SAGE Knowledge
    # 광범위 OA / 학술지 publisher (8)
    "10.3390/":   "mdpi.com",                   # MDPI (catch 52 36 set 정합)
    "10.1111/":   "onlinelibrary.wiley.com",    # Wiley (광범위)
    "10.1002/":   "onlinelibrary.wiley.com",    # Wiley alt prefix
    "10.1007/":   "link.springer.com",          # Springer
    "10.1057/":   "palgrave.com",               # Palgrave / Macmillan
    "10.1093/":   "academic.oup.com",           # Oxford University Press
    "10.1037/":   "psycnet.apa.org",            # APA
    "10.4324/":   "taylorfrancis.com",          # T&F Books
    # 사회과학 / 경제 / 통계 (5)
    "10.1257/":   "aeaweb.org",                 # American Economic Association
    "10.1162/":   "direct.mit.edu",             # MIT Press
    "10.1561/":   "nowpublishers.com",          # Foundations & Trends
    "10.1146/":   "annualreviews.org",          # Annual Reviews
    "10.1525/":   "online.ucpress.edu",         # UC Press
    # STEM / IT (마케팅 인접) (8)
    "10.1145/":   "dl.acm.org",                 # ACM
    "10.1109/":   "ieeexplore.ieee.org",        # IEEE
    "10.1126/":   "science.org",                # Science (catch 52 36 set 정합)
    "10.1038/":   "nature.com",                 # Nature
    "10.1073/":   "pnas.org",                   # PNAS
    "10.1136/":   "bmj.com",                    # BMJ
    "10.1186/":   "biomedcentral.com",          # BMC (BioMed Central)
    "10.1371/":   "plos.org",                   # PLOS (catch 52 36 set 정합)
    # Preprint / Repository (5)
    "10.48550/":  "arxiv.org",                  # arXiv (catch 52 36 set 정합)
    "10.2139/":   "ssrn.com",                   # SSRN (catch 52 36 set 정합)
    "10.31234/":  "osf.io",                     # PsyArXiv
    "10.31219/":  "osf.io",                     # OSF Preprints
    "10.31235/":  "osf.io",                     # SocArXiv
    # Misc (1)
    "10.21511/":  "businessperspectives.org",   # Business Perspectives (소형 OA, §academic-4 Step C-1 발견)
}

# precomputed longest-prefix-first sort (module import 1회)
_DOI_SORTED: List[Tuple[str, str]] = sorted(
    DOI_PREFIX_TO_DOMAIN.items(), key=lambda kv: -len(kv[0])
)


# ── venue/source.display_name → known publisher 도메인 (ACADEMIC_DOMAINS 정합) ─
VENUE_NAME_TO_DOMAIN: Dict[str, str] = {
    "journal of business research": "sciencedirect.com",
    "international journal of research in marketing": "sciencedirect.com",
    "journal of marketing research": "journals.sagepub.com",
    "journal of marketing": "journals.sagepub.com",
    "journal of consumer research": "journals.uchicago.edu",
    "marketing science": "pubsonline.informs.org",
    "journal of advertising": "tandfonline.com",
    "journal of consumer psychology": "onlinelibrary.wiley.com",
    "academy of management journal": "journals.aom.org",
    "academy of management review": "journals.aom.org",
}


def _normalize_host(host: str) -> str:
    """catch 60-b — subdomain dedup: www./m. 제거 + lowercase."""
    h = (host or "").strip().lower()
    if h.startswith("www."):
        h = h[4:]
    elif h.startswith("m."):
        h = h[2:]
    return h


def _domain_of(url: str) -> Optional[str]:
    """URL → host (normalized). 추출 실패 시 None."""
    if not url:
        return None
    try:
        u = url if "://" in url else "https://" + url
        p = urlparse(u)
        h = _normalize_host(p.netloc)
        return h or None
    except Exception:
        return None


def doi_prefix_to_domain(doi: str) -> Optional[str]:
    """DOI prefix → publisher 도메인 (catch 59 정적 table, longest-prefix-first)."""
    if not doi:
        return None
    d = doi.strip()
    for scheme in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(scheme):
            d = d[len(scheme):]
            break
    for prefix, domain in _DOI_SORTED:
        if d.startswith(prefix):
            return domain
    return None


def _venue_name_to_domain(venue: str) -> Optional[str]:
    """venue / source.display_name → known publisher 도메인 (보수적 부분 매칭)."""
    if not venue:
        return None
    v = venue.strip().lower()
    if v in VENUE_NAME_TO_DOMAIN:
        return VENUE_NAME_TO_DOMAIN[v]
    for known, domain in sorted(VENUE_NAME_TO_DOMAIN.items(), key=lambda kv: -len(kv[0])):
        if known in v:
            return domain
    return None


def extract_domain_from_paper(paper: Dict[str, Any], backend: str) -> Optional[str]:
    """학술 paper dict → 도메인 추출 (4-step early-return).

    backend: "semantic_scholar" or "openalex" — schema 분기.
    catch 59 logging fallback: 미매핑 paper 의 DOI 를 logger.warning 박제.
    """
    # (1) primary_location.landing_page_url — OpenAlex 전체 cover
    #     doi.org/* redirect URL 은 DOI prefix 매핑 (3) 이 더 robust 하므로 skip
    if backend == "openalex":
        pl = paper.get("primary_location") or {}
        url = pl.get("landing_page_url") or pl.get("pdf_url") or ""
        if url and "doi.org/" not in url:
            d = _domain_of(url)
            if d:
                return d

    # (2) openAccessPdf.url — Semantic Scholar OA 한정
    if backend == "semantic_scholar":
        oa_pdf = (paper.get("openAccessPdf") or {}).get("url") or ""
        if oa_pdf:
            d = _domain_of(oa_pdf)
            if d:
                return d

    # (3) DOI prefix → publisher 매핑 (catch 59 정적 table)
    if backend == "openalex":
        doi = paper.get("doi") or ""
    else:
        doi = ((paper.get("externalIds") or {}).get("DOI") or "")
    if doi:
        d = doi_prefix_to_domain(doi)
        if d:
            return d

    # (4) venue / source.display_name 매칭
    if backend == "openalex":
        src = ((paper.get("primary_location") or {}).get("source") or {})
        venue = src.get("display_name") or ""
    else:
        venue = paper.get("venue") or ((paper.get("journal") or {}).get("name")) or ""
    if venue:
        d = _venue_name_to_domain(venue)
        if d:
            return d

    # logging fallback — Step C 측정에서 unknown prefix 수집 cycle 대상
    if doi:
        logger.warning(
            "[catch59] unknown DOI prefix (no domain extracted): %s (backend=%s, venue=%r)",
            doi[:60], backend, (venue[:60] if venue else ""),
        )
    return None
