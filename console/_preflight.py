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
import re
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

# —— 字节码纪律：必须在任何本仓 import 之前生效，所以这段不能抽成函数让别人调 ——
# `.pyc` 默认按 (源 mtime, 源 size) 判过期；只要两者相符就用旧字节码，源码内容是否真是那份
# 没人问。`cp -p`、还原备份、部分同步盘都能造出"内容变了而 mtime/size 没变"的文件，
# 于是导入的是盘上不存在的代码。本轮实测踩过两次（详见 console/test_stale_bytecode.py）。
# 指往一个不存在的目录：读必 miss；写由 dont_write_bytecode 挡住，不会在树里留目录。
sys.dont_write_bytecode = True
import os as _bc_os, tempfile as _bc_tf, uuid as _bc_ud
sys.pycache_prefix = _bc_os.path.join(_bc_tf.gettempdir(), "swarmbalance-pyc", _bc_ud.uuid4().hex)

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


def _offstage_prefix():
    """每次运行一个唯一的树外缓存目录：读必 miss，也不会把仓库弄脏。"""
    return os.path.join(tempfile.gettempdir(), "swarmbalance-pyc", uuid.uuid4().hex)


def bytecode_discipline():
    """当前进程实际生效的字节码设置 —— 打印出来，别只信"启动命令里写了"。

    为什么要单独问一遍：环境变量写了不等于生效（解释器可能被 `-E`/`-I` 起、或被
    sitecustomize 改回去）。凡是拿"跑绿了"当证据的地方，都该把这三个值印出来。
    """
    return {"dont_write_bytecode": bool(sys.dont_write_bytecode),
            "pycache_prefix": sys.pycache_prefix,
            "prefix_outside_repo": not str(sys.pycache_prefix or "").startswith(
                str(ROOT)),
            "prefix_under_temp": str(sys.pycache_prefix or "").startswith(
                tempfile.gettempdir())}


def isolated_env(base=None):
    """测量用的子进程环境：UTF-8 输出 + 让树里的 .pyc 够不着。

    为什么必须指到树外：`.pyc` 默认按 (源文件 mtime, size) 校验。用 `cp -p`/还原备份
    改过源码时，新源码可以**保留旧 mtime**，只要长度也碰巧一样，旧 .pyc 就"仍然相符"，
    于是导入的是盘上已经不存在的代码 —— 而计数、skip 归因、断言全都变成在测缓存。
    本轮实测过一次：系统 python 直接跑 `console.test_run_determinism` 报 7 个错，
    栈里那一行 `env = _load()` 在当前源文件里 grep 命中 0；删掉那个 3.13 旧 pyc 后同一条命令 OK。

    所以凡"要给人当一个数字来源"的子进程都走这里：读不到树内缓存就只能从源码编译。

    注意这条只管**子进程**。同进程内的 `import` 与 `importlib.util.spec_from_file_location`
    不受它影响 —— 那是另一条路，靠本文件顶部那三行裸赋值（每个入口脚本都得在自己
    import 本仓任何东西之前复制一份，因为那时还没有本项目可 import）。
    实测对照见 `console/test_stale_bytecode.py::test_in_process_importlib_is_the_gap`。
    """
    out = dict(base if base is not None else os.environ)
    out["PYTHONUTF8"] = "1"
    out["PYTHONIOENCODING"] = "utf-8"
    out["PYTHONDONTWRITEBYTECODE"] = "1"
    # 指往一个不存在的目录：读必miss，写又被 DONTWRITEBYTECODE 挡住，不会在树里留东西
    out["PYTHONPYCACHEPREFIX"] = sys.pycache_prefix or _offstage_prefix()
    return out


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


_CHILD_SKIP = r'''
import json, sys, unittest
top = sys.argv[1]
suite = unittest.TestLoader().discover("console", pattern="test_*.py", top_level_dir=top)
res = unittest.TextTestRunner(stream=open(__import__("os").devnull, "w"), verbosity=0).run(suite)
out = {
    "tests": res.testsRun,
    "failures": len(res.failures),
    "errors": len(res.errors),
    "skipped": [[t.id(), str(rin)] for t, rin in res.skipped],
}
sys.stdout.write(json.dumps(out, ensure_ascii=False))
'''


def collect_skips(interpreter=None):
    """跑一遍 console 发现，返回 {tests, failures, errors, skipped:[[test_id, reason], ...]}。

    为什么解析结果对象而不是 grep `-v` 文本：第一版我用正则去匹配 `skipped '...'`，
    而原因里带换行（explain() 本来就是多行），12 条只认出 1 条 —— 幸好这条探针会自报
    "扫到几条"，才当场暴露。`result.skipped` 是 (test, reason) 的列表，不用猜格式。
    """
    import json
    import subprocess

    exe = interpreter or sys.executable
    proc = subprocess.run([exe, "-c", _CHILD_SKIP, str(ROOT)], cwd=str(ROOT),
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env=isolated_env())
    line = [l for l in proc.stdout.splitlines() if l.startswith("{")]
    if not line:
        raise RuntimeError("子进程没吐结果（exit=%d）：%s"
                           % (proc.returncode, (proc.stderr or "")[-600:]))
    return json.loads(line[-1])


_SKIP_BUCKET_NOTE = "缺包 -> 测试模块 -> 用例数"


def _pkgs_of(reason: str) -> str:
    """从 skip 原因里取缺的包名。

    两种来源都要认：① `_preflight.explain()` 写的「缺少依赖：X（pip 包名：Y）」；
    ② 别的用例自己写的 `No module named 'X'`（常裹在整段 traceback 里）。
    只认一种格式，就会把一半 skip 归到"没写缺哪个包"，等于归因白做。
    """
    m = re.search(r"缺少依赖：([^（）\n]+)", reason)
    if m:
        return m.group(1).strip()
    mods = re.findall(r"No module named '([^']+)'", reason)
    if mods:
        return ", ".join(dict.fromkeys(mods))
    m2 = re.search(r"缺(?:少)?依赖\S*?\s*[:：]?\s*([\w, ]+)", reason)
    if m2:
        return m2.group(1).strip()
    return "(原因里没写缺哪个包)"


def bucket_skips(skipped):
    """[(test_id, reason)] -> {(缺的包, 模块): 条数}，并原样保留识别失败的情况。"""
    buckets = {}
    for tid, reason in skipped:
        pkgs = _pkgs_of(reason)
        m2 = re.search(r"(console/\S+?\.py(?:::\S+)?)", reason)
        mod = m2.group(1) if m2 else (tid.rsplit(".", 2)[0] if "." in tid else tid)
        buckets[(pkgs, mod)] = buckets.get((pkgs, mod), 0) + 1
    return buckets


def render_skips(skipped) -> str:
    if not skipped:
        return "（本次运行没有 skip）"
    buckets = bucket_skips(skipped)
    lines = []
    for (pkgs, mod), n in sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append("  缺 %-40s -> %-50s %d 条不可跑" % (pkgs, mod, n))
    lines.append("  合计 %d 条 skip，分布在 %d 个「缺包 x 模块」组合上（%s）"
                 % (len(skipped), len(buckets), _SKIP_BUCKET_NOTE))
    return "\n".join(lines)


def list_skips(interpreter=None) -> int:
    """真跑一遍，把 skip 归因打印出来：`skipped=12` 不该被读成"过了 12 条"。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 老解释器没有 reconfigure，退化成原样输出
        pass
    data = collect_skips(interpreter)
    print("解释器：%s" % (interpreter or sys.executable))
    print("Ran %d tests，failures=%d errors=%d skipped=%d"
          % (data["tests"], data["failures"], data["errors"], len(data["skipped"])))
    print(render_skips(data["skipped"]))
    return 0 if (not data["failures"] and not data["errors"]) else 1


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
    if "--skips" in sys.argv[1:]:
        sys.exit(list_skips())
    sys.exit(report())
