import re

# 정규식 상수
RE_WRITE_LINE = re.compile(r"^\s*(write|작성|집필)\s*[:：]\s*(.+)$", re.IGNORECASE)

text = "write: Executive Summary"
m = RE_WRITE_LINE.search(text)
if m:
    verb = m.group(1)   # 'write' / '작성' / '집필'
    title = m.group(2)  # 'Executive Summary'

print(verb)
print(title)