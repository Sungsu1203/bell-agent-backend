# tests/test_outline_rename.py
import re
from typing import Match, Pattern

def rename_h2_by_index(current_outline: str, idx: int, new_title: str) -> str:
    idx_escaped = re.escape(str(idx))
    pattern: Pattern[str] = re.compile(rf'^(##\s*{idx_escaped}\.\s*)(.+)$', flags=re.M)
    def _repl(m: Match[str]) -> str:
        return f"{m.group(1)}{new_title}"
    return pattern.sub(_repl, current_outline)

def test_rename_h2():
    src = """## 1. 서문
## 2. 기존 제목
## 3. 다른 장"""
    out = rename_h2_by_index(src, 2, "프로젝트 개요")
    assert "## 2. 프로젝트 개요" in out
    assert "## 1. 서문" in out
    assert "## 3. 다른 장" in out
