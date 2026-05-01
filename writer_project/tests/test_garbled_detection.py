"""_looks_like_garbled 함수 검증."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.web_rag.utils import _looks_like_garbled

# 실제 인덱스에서 본 패턴들
cases = [
    # (text, expected, description)
    ("", False, "빈 문자열"),
    ("hello world", False, "정상 영어"),
    ("안녕하세요 키성장 시장 분석", False, "정상 한국어"),
    ("표 5-6. 가구당 소득, 지출 및 식료품", False, "정상 PDF 텍스트"),
    ("\ufffd\ufffd\ufffd", True, "전부 replacement char"),
    # 학교 HWP 청크 패턴 (실제 진단 결과 기반)
    ("\ufffd8IP9\ufffd:3Z\ufffd\ufffd\ufffd+3`\ufffd\ufffdObj\ufffd1", True, "학교 HWP 깨진 청크"),
    # 옥션 XLSX 청크 패턴
    ("\ufffd\ufffd+{Z\"^\ufffdy\ufffd\ufffdd t\ufffd\ufffd,\ufffd\ufffdf\ufffd", True, "옥션 XLSX 깨진 청크"),
    # 경계: 1% 미만은 통과
    ("\ufffd" + "a" * 200, False, "200자 중 1개 (0.5%) — 통과"),
    # 경계: 1% 초과는 검출
    ("\ufffd\ufffd" + "a" * 100, True, "100자 중 2개 (2%) — 검출"),
    # 단어 사이 가끔 들어간 \ufffd는 깨진 게 아닐 수도 있지만, 1% 초과면 검출
    # → 이 임계값은 "정상 텍스트는 0%, 깨진 텍스트는 40%+"라는 데이터에 기반
]

failed = 0
for text, expected, desc in cases:
    got = _looks_like_garbled(text)
    status = "ok" if got == expected else "FAIL"
    if status == "FAIL":
        failed += 1
    text_preview = text[:30] + "..." if len(text) > 30 else text
    print(f"  [{status:4s}] {desc:35s} | expected={expected!s:5s} got={got!s:5s} | {text_preview!r}")

print(f"\n{'PASS' if failed == 0 else f'FAILED ({failed} cases)'}")
sys.exit(0 if failed == 0 else 1)