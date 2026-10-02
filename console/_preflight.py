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


def current_command():
    """把当前命令行还原成 "<脚本名> <参数...>"，供哨兵打印可直接照抄的重跑命令。"""
    argv = list(sys.argv)
    if not argv:
        return ""
    return " ".join([Path(argv[0]).name] + argv[1:])


ENV_SHORTFALL_RC = 3


def env_shortfall(rc, output=""):
    """子进程是"环境不够"还是"真跑挂了"—— 判据要稳定，别去匹配 traceback 的字样。

    为什么要单独收口：有两处测试原先用 `"No module named" in out` 识别"这台机器跑不了"。
    我给入口加了哨兵之后，输出从 traceback 变成一句人话，那个字符串匹配就失效了，
    两条用例当场从 skip 变 FAIL —— 判据寄生在报错文案上，文案一好它就坏。
    现在认三样：约定的退出码、哨兵的统一标题、以及旧 traceback 字样（向后兼容，
    万一某个入口还没接哨兵）。
    """
    if rc == ENV_SHORTFALL_RC:
        return True
    if not output:
        return False
    return ("缺少依赖：" in output) or ("No module named" in output)


def guard_or_exit(needed, entry="这条命令"):
    """运行入口的依赖哨兵：缺包就打印一句人话并以 3 退出，别丢 traceback。

    为什么需要：`_preflight` 原先只护测试那条路，而 README「快速开始」里第一个
    **应用**命令（`cd frontend && python evaluate_metrics.py ...`）在没建 venv 的机器上
    直接抛 `ModuleNotFoundError: No module named 'shapely'`。评审看到的就是满屏栈，
    他会读成"仿真坏了"，不会想到"我解释器不对"—— 与本轮修掉的那类失败一模一样。

    退出码选 3：与"跑成功 0"、"参数/用法错 2"、"仿真内部异常 1"都不同，
    这样"环境不够"在 CI 与文档自检里都能被单独识别。
    """
    miss = missing(needed)
    if not miss:
        return 0
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 老解释器没有 reconfigure
        pass
    cmd = current_command()
    print("")
    print("=" * 78)
    print(explain(needed, audience="app", rerun=cmd))
    print("=" * 78)
    print("这一步不是仿真出错：是解释器/依赖不够。上面第一行就是缺的包名。")
    return 3


def missing(needed) -> list:
    """返回装不上的模块名。用 find_spec + 真 import 双重判，避免半成品模块骗人。"""
    out = []
    for name in needed:
        try:
            importlib.import_module(name)
        except BaseException:      # 含 ImportError 与被依赖拖垮的其它异常
            out.append(name)
    return out


def explain(needed, gated_modules=None, audience="test", rerun=None) -> str:
    """给读者的一句人话：缺什么 ⇒ 哪条路不可跑 ⇒ 用哪个解释器重跑。

    audience="test"（默认）：面向 unittest 的 skip 原因，措辞是"受影响测试模块"。
    audience="app"：面向 README 里那条**应用**命令（evaluate_metrics.py 等），
    这时"测试模块"和"跑 discover"都是误导，得换成入口本身与同一条命令的重跑写法。
    """
    miss = missing(needed)
    if not miss:
        return ""
    pip_list = " ".join(DEPS.get(m, m) for m in miss)
    lines = ["缺少依赖：%s（pip 包名：%s）" % (", ".join(miss), pip_list)]
    if audience == "app":
        pass                     # 入口与重跑命令在下面的 rerun 行里给全
    elif gated_modules:
        lines.append("受影响测试模块：%s" % ", ".join(gated_modules))
    vp = venv_python()
    if vp:
        lines.append("本项目正式解释器：%s" % vp)
        if audience == "app":
            again = ("%s %s" % (vp, rerun)) if rerun else ("%s <同一条命令>" % vp)
            lines.append("请用该解释器重跑同一条命令，而不是判定仿真出错：%s" % again)
        else:
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

    为什么要临时把 frontend/ 放进 sys.path：内核自己用扁平 import（`from drone import ...`），
    只按路径 exec 它的话，`drone` 这个同级模块找不到 —— 于是这条守门用例在**两个解释器下
    都 skip**（实测原因是 `ModuleNotFoundError: No module named 'drone'`），
    等于一条永不运行的门。加路径只是为了让扁平 import 解析得到；
    文件身份仍由断言 `module.__file__ == path` 保证，且用完就把 sys.path 还原，
    不把 `environment` 这个名字塞进 sys.modules（那是另一类撞车事故）。
    """
    import importlib.util

    path = ROOT / "frontend" / "environment.py"
    if not path.is_file():
        raise AssertionError("内核文件不存在：%s" % path)
    pkg_dir = str(path.parent)
    spec = importlib.util.spec_from_file_location("swarmbalance_kernel_environment", path)
    if spec is None or spec.loader is None:
        raise AssertionError("无法为 %s 建 spec（加载器不可用）" % path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, pkg_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(pkg_dir)
        except ValueError:
            pass
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


_CHILD_MARK = "__PREFLIGHT_JSON__\t"

_CHILD_SKIP = r'''
import io, json, sys, unittest
top = sys.argv[1]
MARK = "__PREFLIGHT_JSON__\t"
_stdout0, _stderr0 = sys.__stdout__, sys.__stderr__
suite = unittest.TestLoader().discover("console", pattern="test_*.py", top_level_dir=top)
_buf = io.StringIO()
# verbosity=1，不是 0：A/B 逐行比对时唯一一处实质差异就是进度点行（`..F.`）——
# 改前那条 `python -m unittest discover` 默认 verbosity=1。用 0 就等于为了"合成一遍"
# 顺手把一种输出关掉，那属于丢信息，不属于省时间。
# warnings='default' 同理，而且这次丢的是 896 行：`unittest.main()` 默认给 runner 传
# warnings='default'，手写的 TextTestRunner 不传就等于让 ResourceWarning 回到默认
# 过滤器（对它恰好是 ignore）—— 真套件 A/B 实测改前 939 行、改后 43 行，缺的全是这类诊断。
res = unittest.TextTestRunner(stream=_buf, verbosity=1, warnings="default").run(suite)
data = {
    "tests": res.testsRun,
    "failures": len(res.failures),
    "errors": len(res.errors),
    # 失败正文必须跟着 JSON 一起回来：以前这一段是父进程用 `unittest discover` 真跑的，
    # 红的时候能把 traceback 打给人看。若只报计数不报正文，就变成"FAIL 但不说为什么"。
    "detail": _buf.getvalue(),
    "skipped": [[t.id(), str(rin)] for t, rin in res.skipped],
}
# 哨兵 + 前后各一个换行：**不能**假设 stdout 干净。有一条测试不带换行地 print 一个以 `{`
# 开头的内容，JSON 就会和它粘成同一行，`startswith("{")` 选中的是那条混合行 ——
# 实测这会让整份诊断归零（A/B 取证：改前 14 行可见、改后 0 行 + JSONDecodeError）。
for _s in (_stdout0, _stderr0):
    try:
        _s.flush()
    except Exception:
        pass
_stdout0.write("\n" + MARK + json.dumps(data, ensure_ascii=False) + "\n")
_stdout0.flush()
'''


def split_sentinel(stdout_text):
    """从子进程 stdout 里取**最后一条**哨兵载荷，其余行原样带回。

    单独成函数是为了让 A/B 那把尺子（`_suite_ab`）复用它而不是照抄一份解析：
    两份解析就会有一份先过期，届时比对口径已经不是产品口径了。
    """
    payload, rest = None, []
    for line in (stdout_text or "").splitlines():
        if line.startswith(_CHILD_MARK):
            payload = line[len(_CHILD_MARK):]      # 取最后一条：哨兵是套件跑完后才写的
        else:
            rest.append(line)
    return payload, rest


def merge_detail(payload, rest, stderr_text, keep_stdout=True):
    """三路合一：runner 正文（哨兵里的 `detail`）+ 子进程 stdout + 子进程 stderr。

    `keep_stdout=False` 只给 A/B 的 M2 消融用（模拟"少接一路"那个真实发生过的回归），
    产品路径永远走 True。
    """
    import json
    detail = json.loads(payload)["detail"]
    if keep_stdout and rest:
        detail += "\n[stdout]\n" + "\n".join(rest)
    if (stderr_text or "").strip():
        detail += "\n[stderr]\n" + stderr_text
    return detail


def run_console_suite(interpreter=None):
    """跑**一遍** console 发现，返回 {tests, failures, errors, skipped, detail}。

    为什么要有这个函数：`release_check` 原先既跑一次 `unittest discover`（给人看正文），
    又调 `collect_skips()`（拿结构化 skip 列表）—— 同一套用例被跑了两遍。本轮实测
    子进程那一遍是 170.884/171.146/172.293 s，父那一遍 152.202 s，两段合起来占全时长的 91.6%。
    现在一次运行同时产出"计数 + skip 清单 + 失败正文"，**没有删掉任何一次真实执行**，
    删掉的是重复的那一次。

    为什么解析结果对象而不是 grep `-v` 文本：第一版我用正则去匹配 `skipped '...'`，
    而原因里带换行（explain() 本来就是多行），12 条只认出 1 条 —— 幸好这条探针会自报
    "扫到几条"，才当场暴露。`result.skipped` 是 (test, reason) 的列表，不用猜格式。

    `detail` 收的是**三路合一**：TextTestRunner 的正文 + 子进程 stdout（测试自己 print 的）
    + 子进程 stderr。少任何一路都是把"看得见"改成"看不见"—— A/B 那次就是少了 stdout 那一路，
    而且被一条 print 粘连直接打崩。哨兵行本身不进 detail，免得 JSON 整份再抄一遍。
    """
    import json
    import subprocess

    exe = interpreter or sys.executable
    proc = subprocess.run([exe, "-c", _CHILD_SKIP, str(ROOT)], cwd=str(ROOT),
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env=isolated_env())
    payload, rest = split_sentinel(proc.stdout)
    if payload is None:
        raise RuntimeError("子进程没吐结果（exit=%d）：%s"
                           % (proc.returncode, ((proc.stdout or "")[-300:] +
                                                (proc.stderr or "")[-600:])))
    info = json.loads(payload)
    if "detail" not in info:
        raise RuntimeError("子进程回来的 JSON 缺 detail —— 覆盖面不能靠猜")
    info["detail"] = merge_detail(payload, rest, proc.stderr)
    return info


def collect_skips(interpreter=None):
    """兼容入口：现在只是 `run_console_suite()` 的别名。

    为什么留着而不是删：`python console/_preflight.py --skips` 与别的会话可能按这个名字调它。
    它的语义仍然是"跑一遍 console 发现，返回 {tests, failures, errors, skipped}"—— 一模一样，
    只是调用方不再一边跑 discover 一边调它（那才是两遍的来源）。
    """
    return run_console_suite(interpreter)


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


_WARN_EMIT = re.compile(r"^(?P<loc>.*?:\d+): (?P<cls>[A-Z]\w*Warning): ")
_WARN_MENTION = re.compile(r"\b([A-Z]\w*Warning)\b")


def warning_census(detail: str) -> str:
    """数**带出处的 warning 发射行**（`文件:行号: XWarning: …`），供调用方印成一行**报告**（不参与退出码）。

    0 也要印：`warnings=0` 与"通道被静音所以数不到"是两件事，只有把数字摆出来才分得开
    （这轮的教训就是静音了 92 条而没人知道 —— 因为绿跑时那一路根本没人看）。

    为什么不能按类名在全文里计数（上一版就是这么写的，本轮被自己的数抓了）：真套件报
    `ResourceWarning:6`，而盘上真正漏的句柄只有 **2** 个。多出的 4 次是
    ① 采集器自己印的 `[PF_WARN_CENSUS]` / `[PF_WARN_CHANNEL]` 两行，
    ② Python 给每条 warning 追加的 `Enable tracemalloc …` 伴行 ——
    **计数被量具自己占掉**就会骗人，和"0 要分『没有』与『看不见』"是同一族错。
    所以两个数并排印：`带出处=` 是真发射次数，`全文提及=` 把自占的那部分留着看得见，不抹掉。
    """
    import collections
    located = collections.Counter()
    mentions = collections.Counter()
    for line in (detail or "").splitlines():
        m = _WARN_EMIT.match(line.strip())
        if m:
            located[m.group("cls")] += 1
        for mm in _WARN_MENTION.finditer(line):
            mentions[mm.group(1)] += 1
    if not located and not mentions:
        return "warnings=0"
    keys = sorted(set(located) | set(mentions))
    return ("warnings=%s 带出处=%d 全文提及=%d"
            % (",".join("%s:%d" % (k, located[k]) for k in keys),
               sum(located.values()), sum(mentions.values())))


def summary_line(detail: str) -> str:
    """从 detail 里挑那一行给人看的裁决（`OK` / `FAILED (failures=…)`）。

    两条约束都是实测撞出来的：
    1. 不能取"最后一行"：detail 是三路合一，末行很可能是某条测试自己的 print
       （实测就变成 `[ESCAPE_MECHANISM] import=…`），扫输出找 "OK" 的人会读不到结果。
    2. **也不能在合并后的全文里倒着找**：`[stdout]`/`[stderr]` 两段追加在 runner 正文之后，
       只要有一条测试打印以 `OK` / `ERROR` 开头的行，它就会盖掉真裁决。所以先截到
       第一个段标头之前，只在 runner 自己写的那段里找。
    """
    text = detail or ""
    cut = len(text)
    for mark in ("\n[stdout]", "\n[stderr]"):
        i = text.find(mark)
        if 0 <= i < cut:
            cut = i
    lines = [l.strip() for l in text[:cut].splitlines() if l.strip()]
    for l in reversed(lines):
        if l.startswith("OK") or l.startswith("FAILED (") or l.startswith("ERROR"):
            return l
    for l in reversed(lines):
        if l.startswith("Ran "):
            return l
    return lines[-1] if lines else ""


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
