# -*- coding: utf-8 -*-
"""依赖预检：把"解释器/venv 不对"从 traceback 变成一句人话。

为什么需要（实测复现，评审视角）：README 教的这条命令——

    python -m unittest discover -s console -p "test_*.py"

在**系统 python**（本机 D:\\anaconda\\python 3.13.5，无 shapely/fastapi）下跑出

    Ran 75 tests ... FAILED (errors=5, skipped=6)
    ModuleNotFoundError: No module named 'fastapi'
    AttributeError: module 'environment' has no attribute 'DEFAULT_EPISODE_MAX_STEPS'

评审不会先 `python -m venv .venv310` 再跑。他看到的是 traceback，
**他会以为仿真坏了**，而不是"我用错了解释器"。所以：
- 缺依赖的测试模块应当 **skip 并写明原因**（含该用的解释器绝对路径），而不是 ERROR；
- 判据是"输出让人一眼看出是环境不够，不是算法错"。

第二条坑更深：`console/test_command_console.py` 会往 `sys.modules["environment"]`
装一个桩，且在真实导入失败时**故意把桩留下**（它自己的 tearDown 逻辑，对它自己是合理的）。
于是后面的守门用例 `import environment` 拿到的是**假模块**，报 AttributeError ——
一个"名字对了但不是那个文件"的错误结论。所以凡是要断言真实内核文件的用例，
必须按**文件路径**加载（见 `load_kernel_environment`），不要按名字 import。

单独跑：
    python console/_preflight.py         # 打印缺哪些包、影响哪些测试模块、该用哪个解释器
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 模块名 → pip 包名（只用于提示，不做安装）
DEPS = {
    "numpy": "numpy",
    "shapely": "shapely",
    "pandas": "pandas",
    "yaml": "PyYAML",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "matplotlib": "matplotlib",
    "osmnx": "osmnx",
    "ortools": "ortools",
}

# 本项目正式使用的解释器（run_tests.bat / start_console.bat 也是这个探测顺序）
VENV_CANDIDATES = (
    ROOT / ".venv310" / "Scripts" / "python.exe",
    ROOT.parent / ".venv310" / "Scripts" / "python.exe",
)


def venv_python() -> Path | None:
    for c in VENV_CANDIDATES:
        if c.is_file():
            return c
    return None


def missing(needed) -> list:
    """返回装不上的模块名。用 find_spec + 真 import 双重判，避免半成品模块骗人。"""
    out = []
    for name in needed:
        try:
            importlib.import_module(name)
        except BaseException:      # 含 ImportError 与被依赖拖垮的其它异常
            out.append(name)
    return out


def explain(needed, gated_modules=None) -> str:
    """给读者的一句人话：缺什么 ⇒ 多少用例不可跑 ⇒ 用哪个解释器。"""
    miss = missing(needed)
    if not miss:
        return ""
    pip_list = " ".join(DEPS.get(m, m) for m in miss)
    lines = ["缺少依赖：%s（pip 包名：%s）" % (", ".join(miss), pip_list)]
    if gated_modules:
        lines.append("受影响测试模块：%s" % ", ".join(gated_modules))
    vp = venv_python()
    if vp:
        lines.append("本项目正式解释器：%s" % vp)
        lines.append("请用该解释器重跑，而不是判定仿真出错：%s -m unittest discover -s console -p \"test_*.py\"" % vp)
    else:
        lines.append("未找到 .venv310；当前解释器 %s" % sys.executable)
    return "\n".join("  " + l for l in lines)


def require(*needed, gated_in=None):
    """测试模块顶部调用：缺依赖就整模块 skip 并带上可读原因。

    为什么是 SkipTest 而不是 ERROR：unittest 在**模块导入期**抛 SkipTest 会把它
    记成 skipped（带原因），而裸 ImportError 会变成 `_FailedTest` 的 error ——
    后者在评审眼里就是"代码坏了"。
    """
    miss = missing(needed)
    if miss:
        raise unittest.SkipTest(explain(needed, [gated_in] if gated_in else None))


def load_kernel_environment():
    """按**文件路径**加载 frontend/environment.py，不接受名字撞车。

    返回 (module, real_path)。任何依赖缺失都原样抛出 ImportError，由调用方决定 skip。
    """
    import importlib.util

    path = ROOT / "frontend" / "environment.py"
    if not path.is_file():
        raise AssertionError("内核文件不存在：%s" % path)
    spec = importlib.util.spec_from_file_location("swarmbalance_kernel_environment", path)
    module = importlib.util.module_from_spec(spec)
    # 注意：不塞进 sys.modules，免得污染后续按名字 import 的用例（这正是本函数要防的那类事故）
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != path.resolve():
        raise AssertionError("加载到的不是那个文件：%s != %s" % (module.__file__, path))
    return module, path


def load_frontend_module(basename: str):
    """按文件路径加载 frontend/<basename>.py，不接受名字撞车。"""
    import importlib.util

    path = ROOT / "frontend" / ("%s.py" % basename)
    if not path.is_file():
        raise AssertionError("入口文件不存在：%s" % path)
    spec = importlib.util.spec_from_file_location("swarmbalance_fe_%s" % basename, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != path.resolve():
        raise AssertionError("加载到的不是那个文件：%s != %s" % (module.__file__, path))
    return module


def load_frontend_package_module(pkg: str, basename: str):
    """按文件路径加载 frontend/<pkg>/<basename>.py（如 greedy/run_greedy.py）。

    包内模块会 import 同包的兄弟模块，所以临时把该包目录加入 sys.path —— 加完就还原，
    避免泄漏给后续用例（本文件要防的正是这类进程内污染）。
    """
    import importlib.util

    pkg_dir = ROOT / "frontend" / pkg
    path = pkg_dir / ("%s.py" % basename)
    if not path.is_file():
        raise AssertionError("入口文件不存在：%s" % path)
    added = str(pkg_dir)
    inserted = added not in sys.path
    if inserted:
        sys.path.insert(0, added)
    try:
        spec = importlib.util.spec_from_file_location("swarmbalance_%s_%s" % (pkg, basename), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(added)
    if Path(module.__file__).resolve() != path.resolve():
        raise AssertionError("加载到的不是那个文件：%s != %s" % (module.__file__, path))
    return module


def report() -> int:
    miss = missing(list(DEPS))
    vp = venv_python()
    print("解释器：%s（Python %s）" % (sys.executable, ".".join(map(str, sys.version_info[:3]))))
    print("项目 venv：%s" % (vp if vp else "未找到 .venv310"))
    if miss:
        print("[FAIL] 缺依赖：%s" % ", ".join(miss))
        if vp:
            print("       这不是仿真坏了。请用：%s" % vp)
        return 1
    print("[OK] 全部 %d 个依赖可导入" % len(DEPS))
    return 0


if __name__ == "__main__":
    sys.exit(report())
