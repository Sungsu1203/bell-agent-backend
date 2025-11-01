# chap14_8/__init__.py
import sys
from importlib import import_module

for name in ("core", "utils", "agent", "tools", "content"):
    pkg = import_module(f"chap14_8.{name}")
    sys.modules.setdefault(name, pkg)