# smoke_auto_footnote.py
import os, re

# ⬇️ 실제 함수가 있는 모듈 경로로 변경하세요!
# 예) from utils.auto_footnote import attach_auto_citations
from main import attach_auto_citations  # <-- 수정

# 인라인 표기 테스트를 위해 on
os.environ["AUTO_FOOTNOTE_MAX"] = "12"
os.environ["AUTO_FOOTNOTE_INLINE"] = "1"

# 더미 Document 흉내 (LangChain Document 처럼 .metadata 속성만 있으면 됨)
class DummyDoc:
    def __init__(self, metadata): self.metadata = metadata

# 본문에 IEA/OECD/KDI 키워드를 일부러 넣어서 인라인 [^n] 달리게 하기
text = """한국의 배터리 정책은 IEA 보고서와 OECD 권고를 참고한다.
배경 설명… KDI 브리프도 참조한다.
"""

# refs는 Document/dict 섞여도 작동해야 함
state = {
    "references": {
        "docs": [
            DummyDoc({"source": "https://www.iea.org/reports/global-ev-outlook-2025",
                      "title": "Global EV Outlook 2025"}),
            {"metadata": {"url": "https://www.oecd.org/energy/foo.pdf",
                          "title": "OECD Energy Note"}},
            DummyDoc({"metadata": {"source": "https://eiec.kdi.re.kr/policy/domesticView.do?ac=0000190998",
                                   "title": "KDI 정책자료"}}),
        ]
    }
}

out = attach_auto_citations(text, state)

# ── 간단 검증 ─────────────────────────────────────────────────────────
assert "### 참고 문헌 / 각주" in out, "각주 블록 헤더가 없습니다."
# 인라인 [^n]이 최소 1개 이상 달렸는지 확인
assert re.search(r"\[\^\d+\]", out), "본문에 인라인 각주 마커가 보이지 않습니다."
# 각주 목록에 URL이 포함됐는지 확인
assert "iea.org" in out and "oecd.org" in out and "kdi.re.kr" in out, "각주 URL 누락"

print("==== OUTPUT (preivew) ====")
print(out.splitlines()[-10:])  # 마지막 10줄만 프리뷰
print("✅ smoke ok")
