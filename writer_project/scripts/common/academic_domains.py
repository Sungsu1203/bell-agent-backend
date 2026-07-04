"""공유 학술 도메인 set — § 없는 중립 폴더(scripts/common).

R2-a 이관: §academic-1/measure_ab.py 인라인 정의를 글자 하나 안 바꾸고 이관.
§paper-writer-1/measure_paper.py axis3 경로에서도 vertex chunk 학술/비학술
가름에 공유 참조하기 위해 분리. 도메인 추가·수정·삭제는 별 작업 — 순수 이동만.
"""

# ── academic domains (§academic-1 B1 29 + §academic-3 B +7 + §academic-4 Phase 2 +4 = 40) ──
ACADEMIC_DOMAINS = {
    # Korean academic society / aggregator / search engine
    "dbpia.co.kr", "kadpr.or.kr", "kci.go.kr", "kiss.kstudy.com", "riss.kr",
    "academic.naver.com",          # §academic-3 (academic search, naver_direct hit)

    # Global academic society (advertising / marketing)
    "ama.org", "mmaglobal.com", "msi.org", "pubsonline.informs.org",
    "aom.org",                     # §academic-3 (Academy of Management root)

    # Global publisher (peer-review)
    "academic.oup.com", "emerald.com", "journals.sagepub.com",
    "link.springer.com", "onlinelibrary.wiley.com", "plos.org",
    "sagepub.com", "science.org", "springer.com", "tandfonline.com", "wiley.com",
    "mdpi.com",                    # §academic-3 (OA publisher, marketing journals)
    "sciencedirect.com",           # §academic-3 (Elsevier root, JBR / JoR cover)

    # Global preprint repository
    "arxiv.org", "papers.ssrn.com", "ssrn.com",

    # Global academic archive
    "jstor.org", "pmc.ncbi.nlm.nih.gov",

    # Global academic search engine / scholarly metadata
    "doaj.org", "openalex.org", "semanticscholar.org",

    # Global advertising / marketing journal (peer-review, Sungsu 분야 정합)
    "acr-journal.com",             # §academic-3 (Assoc. for Consumer Research)
    "journalofadvertising.org",    # §academic-3 (Journal of Advertising; catch 45 별 cycle)

    # Global academic SNS (peer-review working paper hosting)
    "researchgate.net",            # §academic-3 (working paper self-archive)

    # Global industry research repository (advertising-specific)
    "warc.com",

    # §academic-4 Phase 2 commit 3 영역 추가 (catch 67 영역)
    # 대학 publication + 소형 OA — vertex 학술 영역 hit 정합 (Step C-1 commit 2 2차 측정)
    "digital.hec.ca",              # HEC Montreal — Canadian business school publication
    "docs.rwu.edu",                # Roger Williams University — academic repository
    "knowledge.insead.edu",        # INSEAD business school — research knowledge base
    "journal.seisense.com",        # SEISENSE Journal — OA 학술 (multidisciplinary)
}
