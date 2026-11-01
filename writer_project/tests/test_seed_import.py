"""§paper-writer-2 V1 — seed_import 회귀 테스트 (오프라인, 비용 0).

원칙 (CC_PROMPT_20261024 B0):
  1. 조용히 버리지 않는다 → 격리된 항목이 review.json 에 사유와 함께 남는지 단언.
  2. 고치기 전에 재현 테스트부터 → F1~F4 각 결함을 재현하는 고정 입력으로 단언.
  3. 테스트는 네트워크 없이 돈다 → OpenAlex 응답은 녹화 파일(oa_batykov_raw.json)로.

실행:
    cd writer_project && ../.venv_vertex/bin/python -m pytest tests/test_seed_import.py -q
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]                 # writer_project/
FIX = Path(__file__).parent / "fixtures" / "seed_import"
SEED_IMPORT = ROOT / "scripts" / "§paper-writer-1" / "seed_import.py"
SEEDS = ROOT / "scripts" / "§paper-writer-1" / "seeds"
BASE_SEED = SEEDS / "seed_references_trademark-similarity.json"
COMMITTED_MANUAL = SEEDS / "seed_references_trademark-similarity+manual.json"

# 무한루프 회귀(F2)를 '멈추지 않음' 으로 잡기 위한 상한. 정상 실행은 2초 미만.
RUN_TIMEOUT_S = 30


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """in-process 테스트가 네트워크를 쓰면 즉시 터뜨린다 (원칙 3 양성 대조).

    subprocess 로 돌리는 테스트에는 걸리지 않는다 — seed_import.py 자체가
    socket/urllib 을 import 하지 않는다는 사실로 보증하고, 그것은
    test_seed_import_imports_no_network 가 단언한다.
    """
    def _boom(*a, **k):
        raise RuntimeError("테스트 중 네트워크 접근 시도")
    monkeypatch.setattr(socket, "socket", _boom)


def run_import(src: Path, out: Path | None = None, base: Path | None = None):
    """seed_import.py 를 CLI 그대로 실행. 반환: (CompletedProcess, out_json, review_json)."""
    cmd = [sys.executable, str(SEED_IMPORT), str(src)]
    if base:
        cmd += ["--base", str(base)]
    if out:
        cmd += ["--out", str(out)]
    else:
        cmd += ["--dry"]
    p = subprocess.run(cmd, capture_output=True, text=True,
                       timeout=RUN_TIMEOUT_S, cwd=ROOT)
    data = review = None
    if out and out.exists():
        data = json.loads(out.read_text(encoding="utf-8"))
        rv = out.with_name(out.name + ".review.json")
        if rv.exists():
            review = json.loads(rv.read_text(encoding="utf-8"))
    return p, data, review


def codes_for(review: dict, key: str) -> list[str]:
    for it in review["items"]:
        if it["key"] == key:
            return it["codes"]
    return []


def item_for(review: dict, key: str) -> dict | None:
    for it in review["items"]:
        if it["key"] == key:
            return it
    return None


# ── F1: 비라틴 제목이 빈 문자열로 접혀 서로 중복 처리되던 결함 ──────────
def test_f1_nonlatin_titles_not_collapsed(tmp_path):
    out = tmp_path / "f1.json"
    p, data, review = run_import(FIX / "f1_nonlatin_dup.bib", out)
    assert p.returncode == 0, p.stderr
    titles = [r["title"] for r in data["references"]]
    assert len(data["references"]) == 2, titles
    assert any(t.startswith("Первая") for t in titles)
    assert any(t.startswith("Вторая") for t in titles)      # 구 구현은 이게 사라졌다
    assert data["manual_import"]["added"] == 2
    # 비라틴 제목은 WARN 으로 표시되나 주입은 된다
    for key in ("ru_a_2021", "ru_b_2022"):
        assert "NON_LATIN_TITLE" in codes_for(review, key)
        assert item_for(review, key)["injected"] is True


# ── F2: 닫히지 않은 큰따옴표 → 무한루프 ────────────────────────────────
def test_f2_unterminated_quote_terminates_and_quarantines(tmp_path):
    out = tmp_path / "f2.json"
    # 구 구현은 여기서 멈추지 않아 TimeoutExpired 가 났다 (exit 137 재현).
    p, data, review = run_import(FIX / "f2_unterminated_quote.bib", out)
    assert p.returncode == 0, p.stderr
    assert data["references"] == [], "PARSE_ERROR 항목은 주입되지 않는다"
    it = item_for(review, "bad_quote_2020")
    assert it is not None and it["grade"] == "ERROR"
    assert "PARSE_ERROR" in it["codes"]
    assert it["injected"] is False
    assert it["parse_detail"], "복구 사유가 기록되어야 한다 (조용히 버리지 않는다)"


# ── F3: LaTeX 이스케이프 잔존 ──────────────────────────────────────────
def test_f3_latex_escapes_restored(tmp_path):
    out = tmp_path / "f3.json"
    p, data, _ = run_import(FIX / "f3_latex_escapes.bib", out)
    assert p.returncode == 0, p.stderr
    titles = [r["title"] for r in data["references"]]
    assert "Müller and Café: Brand & Trademark Similarity" in titles
    assert "François on Trademark Distinctiveness" in titles
    for r in data["references"]:
        assert "\\" not in r["title"], r["title"]
        assert "\\" not in (r["authors_short"] or "")


# ── F4: '@' 단독 필터의 위양성 ─────────────────────────────────────────
def test_f4_atsign_title_kept_but_email_quarantined(tmp_path):
    out = tmp_path / "f4.json"
    p, data, review = run_import(FIX / "f4_atsign_title.bib", out)
    assert p.returncode == 0, p.stderr
    titles = [r["title"] for r in data["references"]]
    assert "Trademark@Internet: Domain Name Confusion" in titles   # 구 구현은 탈락
    it = item_for(review, "contact_page")
    assert it is not None and it["grade"] == "ERROR"
    assert "EMAIL_LIKE_TITLE" in it["codes"] and it["injected"] is False


# ── 정상 입력: 사유 코드 0 (양성 대조의 반대편) ─────────────────────────
def test_normal_input_has_no_review_codes(tmp_path):
    out = tmp_path / "normal.json"
    p, data, review = run_import(FIX / "normal.bib", out)
    assert p.returncode == 0, p.stderr
    assert len(data["references"]) == 1
    assert review["items"] == [], review["items"]
    assert review["counts"] == {"ERROR": 0, "WARN": 0, "INFO": 0}


# ── B3 사유 코드: ERROR 3종 ────────────────────────────────────────────
@pytest.mark.parametrize("key,code", [
    ("no_title_2020", "NO_TITLE"),
    ("email_title_2020", "EMAIL_LIKE_TITLE"),
    ("bare_2020", "NOT_A_PAPER"),
])
def test_error_codes(tmp_path, key, code):
    out = tmp_path / "err.json"
    p, data, review = run_import(FIX / "codes_error.bib", out)
    assert p.returncode == 0, p.stderr
    assert data["references"] == [], "ERROR 는 주입되지 않는다"
    it = item_for(review, key)
    assert it is not None, f"{key} 가 검토 목록에 없다 — 조용히 버려졌다"
    assert code in it["codes"]
    assert it["grade"] == "ERROR" and it["injected"] is False
    assert it["actions"], "권장 조치가 비어 있다"


# ── B3 사유 코드: WARN 5종 (전부 주입됨) ───────────────────────────────
@pytest.mark.parametrize("key,code", [
    ("no_sec_2021", "NO_SEC_TAG"),
    ("prio_clash", "PRIO_CONFLICT"),
    ("webpage_2015", "WEBPAGE_TYPE"),
    ("near_dup_2021", "NEAR_DUPLICATE"),
    ("no_sec_2021", "NO_DOI"),
])
def test_warn_codes_are_injected_and_listed(tmp_path, key, code):
    out = tmp_path / "warn.json"
    p, data, review = run_import(FIX / "codes_warn.bib", out)
    assert p.returncode == 0, p.stderr
    assert len(data["references"]) == 5, "WARN 은 전부 주입된다"
    it = item_for(review, key)
    assert it is not None and code in it["codes"]
    assert it["grade"] == "WARN" and it["injected"] is True


def test_review_legend_covers_every_emitted_code(tmp_path):
    """사유 코드가 범례에 없으면 사람이 읽을 수 없다 — 코드/문서 동기 단언."""
    out = tmp_path / "legend.json"
    for fx in ("codes_error.bib", "codes_warn.bib", "f2_unterminated_quote.bib"):
        _, _, review = run_import(FIX / fx, out)
        for it in review["items"]:
            for c in it["codes"]:
                assert c in review["legend"], f"{c} 가 legend 에 없다"


# ── 사용자 실데이터: 커밋된 산출과 동일한지 ─────────────────────────────
def test_real_data_reproduces_committed_manual_json(tmp_path):
    """정리본(.bib) + 원본 시드 → references 가 커밋된 +manual.json 과 동일."""
    out = tmp_path / "manual.json"
    p, data, _ = run_import(FIX / "trademark_seed2_clean.bib", out, base=BASE_SEED)
    assert p.returncode == 0, p.stderr
    expected = json.loads(COMMITTED_MANUAL.read_text(encoding="utf-8"))["references"]
    assert data["references"] == expected
    assert len(data["references"]) == 22
    ids = [r["id"] for r in data["references"]]
    assert len(ids) == len(set(ids)), "id 중복"


def test_out_equal_base_is_blocked(tmp_path):
    """원본 보호 — --out 이 --base 와 같으면 거부(exit 2)."""
    base_copy = tmp_path / "base.json"
    base_copy.write_text(BASE_SEED.read_text(encoding="utf-8"), encoding="utf-8")
    before = base_copy.read_bytes()
    p, _, _ = run_import(FIX / "normal.bib", out=base_copy, base=base_copy)
    assert p.returncode == 2, p.stdout
    assert base_copy.read_bytes() == before, "원본이 덮어써졌다"


def test_seed_import_imports_no_network():
    """seed_import.py 가 네트워크 모듈을 import 하지 않는다 (비용 0 보증)."""
    src = SEED_IMPORT.read_text(encoding="utf-8")
    for mod in ("socket", "urllib", "requests", "httpx", "http.client"):
        assert f"import {mod}" not in src, f"{mod} 를 import 한다"


# ── 녹화 OpenAlex 응답: DOI 보유 work 가 드롭되는 결함 (B4 승인 전 xfail) ──
@pytest.mark.xfail(
    reason="B4 미승인 — openalex.py:193-194 가 도메인 미상 work 를 드롭한다. "
           "수정 승인 후 pass 로 전환 (CC_PROMPT_20261024 B2/B4).",
    strict=True,
)
def test_recorded_oa_response_keeps_doi_bearing_works():
    """녹화 응답 10건 중 DOI 를 가진 work 는 하나도 사라지지 않아야 한다.

    현재는 실패가 정상이다 — 4단 폴백이 전부 불발한 work 가 호출처에서 드롭된다.
    """
    sys.path.insert(0, str(ROOT))
    from tools.web_rag._scholarly_domain import extract_domain_from_paper

    body = json.loads((FIX / "oa_batykov_raw.json").read_text(encoding="utf-8"))
    works = body["results"]
    assert len(works) == 10, "녹화 픽스처가 바뀌었다"
    dropped_with_doi = [
        w["display_name"] for w in works
        if (w.get("doi") or "") and not extract_domain_from_paper(w, backend="openalex")
    ]
    assert dropped_with_doi == [], f"DOI 보유 work {len(dropped_with_doi)}건 드롭: {dropped_with_doi}"


def test_recorded_oa_response_documents_current_drop():
    """현재 드롭 실태를 수치로 박제한다 (B4 전후 비교 기준선).

    xfail 테스트가 '고쳐야 할 것' 을 말한다면, 이 테스트는 '지금 어떤지' 를 말한다.
    B4 수정 시 이 테스트의 기대값을 함께 갱신해야 한다 — 그게 변경의 증거가 된다.
    """
    sys.path.insert(0, str(ROOT))
    from tools.web_rag._scholarly_domain import extract_domain_from_paper

    body = json.loads((FIX / "oa_batykov_raw.json").read_text(encoding="utf-8"))
    works = body["results"]
    kept = [w for w in works if extract_domain_from_paper(w, backend="openalex")]
    dropped = [w for w in works if not extract_domain_from_paper(w, backend="openalex")]
    assert len(kept) == 5 and len(dropped) == 5
    # 드롭 5건은 **전부** DOI 보유. 생존 5건 중 DOI 보유는 1건뿐(theses.hal.science).
    # = 드롭 기준은 'DOI 가 있음' 이 아니라 '호스트를 못 찾음' 이고, DOI 만 있는 work 가
    #   정확히 그 경우에 해당한다. 쏠림이 우연이 아님을 수치로 고정한다.
    assert all((w.get("doi") or "") for w in dropped)
    assert sum(1 for w in kept if (w.get("doi") or "")) == 1
    # 생존은 전부 1단계(landing_page_url) 로만 살았다 — DOI prefix 표·venue 표 기여 0
    from tools.web_rag._scholarly_domain import doi_prefix_to_domain
    assert all(not doi_prefix_to_domain(w.get("doi") or "") for w in works)
    # rank#1(정확히 찾던 논문)이 드롭된다는 사실 자체를 박제
    assert works[0]["doi"] == "https://doi.org/10.24158/spp.2020.10.3"
    assert extract_domain_from_paper(works[0], backend="openalex") is None
