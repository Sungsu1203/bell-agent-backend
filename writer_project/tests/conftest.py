"""pytest 수집 설정.

아래 3개는 pytest 테스트가 아니라 **직접 실행용 단독 스크립트**다.
모듈 레벨에 `sys.exit()` 이 있어 pytest 가 수집하는 순간 SystemExit 이 올라가
`pytest tests/` 전체가 INTERNALERROR 로 죽는다(2026-10-29 실측).

스크립트 자체는 정상이다 — 실행법이 다를 뿐이다:
    PYTHONPATH=. ../.venv_vertex/bin/python tests/test_domain_bonus_compat.py
따라서 파일을 고치지 않고 수집에서만 제외한다. pytest 로 돌릴 테스트를
새로 추가할 때는 `def test_*` 함수형으로 쓸 것.
"""
collect_ignore = [
    "test_domain_bonus_compat.py",
    "test_garbled_detection.py",
    "test_xlsx_score_compat.py",
]
