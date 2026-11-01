"""Dependency diagnostics for command-line evaluation, without test-runner state."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

from swarmbalance.paths import PROJECT_ROOT as ROOT
DEPS = {"numpy": "numpy", "shapely": "shapely", "pandas": "pandas"}
VENV_CANDIDATES = (
    ROOT / ".venv310" / "Scripts" / "python.exe",
    ROOT.parent / ".venv310" / "Scripts" / "python.exe",
)


def venv_python() -> Path | None:
    for candidate in VENV_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def missing(needed) -> list:
    """Check actual imports so broken installations are also reported."""
    result = []
    for name in needed:
        try:
            importlib.import_module(name)
        except BaseException:
            result.append(name)
    return result


def guard_or_exit(needed, entry="这条命令"):
    """Return 0 when available, or print diagnostics and return exit code 3."""
    absent = missing(needed)
    if not absent:
        return 0
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    packages = " ".join(DEPS.get(name, name) for name in absent)
    print()
    print("=" * 78)
    print("  缺少依赖：%s（pip 包名：%s）" % (", ".join(absent), packages))
    interpreter = venv_python()
    if interpreter:
        command = " ".join([Path(sys.argv[0]).name] + sys.argv[1:])
        print("  本项目正式解释器：%s" % interpreter)
        print("  请用该解释器重跑同一条命令，而不是判定仿真出错：%s %s"
              % (interpreter, command or entry))
    else:
        print("  未找到 .venv310；当前解释器 %s" % sys.executable)
    print("=" * 78)
    print("这一步不是仿真出错：是解释器/依赖不够。上面第一行就是缺的包名。")
    return 3
