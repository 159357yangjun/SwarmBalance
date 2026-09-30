# -*- coding: utf-8 -*-
"""测量与发布检查的子进程必须读不到树里的 .pyc —— 否则数字描述的是盘上没有的代码。

为什么单独一条：`.pyc` 默认按 (源文件 mtime, size) 判新旧。用 `cp -p`、还原备份、
或某些编辑器/同步盘写文件时，源码内容变了但 **mtime 被按回旧值**，只要长度碰巧不变，
旧缓存就"仍然相符"，import 直接跑旧字节码。本轮就在本机真实踩过：

    $ python -m unittest console.test_run_determinism      # 系统 python 3.13
    ERROR ... AttributeError: 'NoneType' object has no attribute 'loader'
      File "console/test_run_determinism.py", line 31, in <module>
        env = _load()          <- 当前源文件里 grep `_load` 命中 0 次

7 个错全部来自一个 Sep 29 的 `cpython-313.pyc`；把它删掉，同一条命令 `OK (skipped=2)`。
也就是说：**同一份盘上的源码，在两个解释器下跑出的是两个版本的代码**。
README 里的用例数、skip 归因、release_check 的 OK，如果踩上这个都是假的。

两条断言：① 复现"相符的过期缓存会盖住现源码"（不复现就不知道这扇门在防什么）；
② `isolated_env()` 确实把这种缓存挡在门外。
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console._preflight import isolated_env  # noqa: E402

PROBE = ROOT / "console" / "_sb_pyc_probe_tmp.py"
# 两段必须**等长**：size 变了缓存就自失效了，测不到要防的那一类
A_SRC = 'VALUE = "from-A"\n'
B_SRC = 'VALUE = "from-B"\n'
READER = ("import sys; sys.path.insert(0, sys.argv[1]); "
          "import console._sb_pyc_probe_tmp as m; print(m.VALUE)")


def _read(interpreter=None, env=None):
    if env is None:
        # 显式把缓存相关变量摘掉：这条要测的就是"默认按树里的 .pyc 走"
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE")}
    proc = subprocess.run([(interpreter or sys.executable), "-c", READER, str(ROOT)],
                          cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if proc.returncode != 0:
        raise AssertionError("子进程读探针失败：%s" % (proc.stderr or "")[-400:])
    return proc.stdout.strip()


def _probe_pycs():
    d = PROBE.parent / "__pycache__"
    return sorted(p.name for p in d.glob("_sb_pyc_probe_tmp.*.pyc")) if d.is_dir() else []


class StaleBytecodeTests(unittest.TestCase):

    def setUp(self):
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        for p in [PROBE] + [(PROBE.parent / "__pycache__" / n) for n in _probe_pycs()]:
            try:
                p.unlink()
            except FileNotFoundError:
                pass

    def test_isolated_env_actually_isolates(self):
        """先把环境本身钉住：键少了，下面那条复现断言就是空谈。"""
        env = isolated_env()
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertTrue(env["PYTHONPYCACHEPREFIX"], "没指缓存前缀就还是读树里的 .pyc")
        self.assertNotIn(str(ROOT / "console" / "__pycache__"), env["PYTHONPYCACHEPREFIX"])
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")

    def test_matching_stale_pyc_can_shadow_current_source(self):
        """① 复现：内容变了、mtime+size 都没变 -> 普通 import 跑的是旧字节码。

        这一步是为了证明本文件防的不是想象中的问题。若哪天 Python 改成默认按内容
        hash 校验、这条不再成立，它会以"读到的是 from-B"失败，那时该改的是这份说明。
        """
        PROBE.write_text(A_SRC, encoding="utf-8")
        st = os.stat(PROBE)
        self.assertEqual(_read(), "from-A", "基线就不对，探针没跑通")
        self.assertEqual(len(_probe_pycs()), 1, "没生成树内缓存，后面测不到东西")

        PROBE.write_text(B_SRC, encoding="utf-8")          # 等长改写
        os.utime(PROBE, (st.st_atime, st.st_mtime))         # 把 mtime 按回旧值
        self.assertIn("from-B", PROBE.read_text(encoding="utf-8"),
                      "源文件本身没改成 B，下一条断言就是空转")

        self.assertEqual(_read(), "from-A",
                         "过期缓存没盖住现源码 —— 本用例要防的那一类在本机不再成立，"
                         "请连带改这段说明与 isolated_env 的注释")

    def test_isolated_env_avoids_the_stale_pyc(self):
        """② 同一份"过期但相符"的缓存，走 isolated_env 就必须读到现源码。"""
        PROBE.write_text(A_SRC, encoding="utf-8")
        st = os.stat(PROBE)
        _read()  # 生成树内缓存
        PROBE.write_text(B_SRC, encoding="utf-8")
        os.utime(PROBE, (st.st_atime, st.st_mtime))
        self.assertEqual(_read(env=isolated_env()), "from-B",
                         "isolated_env 没能挡住过期缓存，数字仍然可能来自盘上不存在的代码")

    def test_probe_leaves_nothing_in_the_tree(self):
        """这条自身不许在树里留下文件：它会写源码与 .pyc，跑完必须干净。"""
        PROBE.write_text(A_SRC, encoding="utf-8")
        _read()
        _read(env=isolated_env())
        self._cleanup()
        self.assertFalse(PROBE.exists(), "探针源文件留在树里会脏工作树")
        self.assertEqual(_probe_pycs(), [], "探针的字节码没清干净")

    # —— ③ 同进程那一路：isolated_env() 只管子进程，管不到正在跑断言的这个解释器 ——

    ENTRY_POINTS = [
        ("_preflight", "console"),
        ("_citations", "console"),
        ("_readme_counts", "console"),
        ("compare_gate", "results"),
        ("verify_data_provenance", "."),
        ("release_check", "."),
    ]

    def _entry_points(self):
        """出图的入口要 pandas 才能 import；缺它的机器上不能算"纪律没生效"。

        清单本身要有下限：两处循环都遍历这个列表，列表一旦被清空，
        两条断言都会"零次通过" —— 门还在，但已经不拦任何东西了。
        """
        pts = list(self.ENTRY_POINTS)
        import importlib.util
        if importlib.util.find_spec("pandas") is not None:
            pts.append(("plot_compare_metrics", "results"))
        self.assertGreaterEqual(len(pts), 6,
                                "入口清单只剩 %d 条，两处遍历会空转：%s" % (len(pts), pts))
        return pts

    LOAD_BY_PATH = (
        "import sys, pathlib, importlib.util\n"
        "root = sys.argv[1]\n"
        "sys.path.insert(0, root)\n"
        "%(bootstrap)s\n"
        "spec = importlib.util.spec_from_file_location('sb_probe_mod', pathlib.Path(sys.argv[2]))\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "print(m.VALUE)\n")

    def _spawn(self, code, probe, bootstrap="pass"):
        pr = subprocess.run([sys.executable, "-c", code % {"bootstrap": bootstrap},
                             str(ROOT), str(probe)],
                            cwd=str(ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace",
                            env={k: v for k, v in os.environ.items()
                                 if k not in ("PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE")})
        if pr.returncode != 0:
            raise AssertionError("子进程失败：%s" % (pr.stderr or "")[-400:])
        return pr.stdout.strip()

    def _poison(self):
        """造出"内容已是 B、但 mtime+size 仍与 A 的缓存相符"的探针，返回它的路径。"""
        PROBE.write_text(A_SRC, encoding="utf-8")
        st = os.stat(PROBE)
        self._spawn(self.LOAD_BY_PATH, PROBE)          # 先跑一遍，生成树内 .pyc
        PROBE.write_text(B_SRC, encoding="utf-8")      # 等长改写
        os.utime(PROBE, (st.st_atime, st.st_mtime))    # 把 mtime 按回旧值
        self.assertIn("from-B", PROBE.read_text(encoding="utf-8"), "源文件没改成 B，判据空转")
        self.assertEqual(len(_probe_pycs()), 1, "没生成树内缓存，夹具前提不成立")

    def test_in_process_importlib_is_the_gap_and_entries_close_it(self):
        """先证缺口，再证每个入口都把它关上了。

        `isolated_env()` 设的是**子进程**的变量：同进程里的 `import` 和
        `spec_from_file_location` 完全不受它影响（实测：同一份"过期但相符"的缓存，
        默认同进程加载读到 from-A）。所以纪律必须写在每个入口脚本自己头上、
        且在它 import 本仓任何东西之前 —— 这也正是它不能抽成公共函数的原因。
        """
        self._poison()
        try:
            got = self._spawn(self.LOAD_BY_PATH, PROBE)
            self.assertEqual(got, "from-A",
                             "缺口没复现（读到 %s）：同进程 importlib 本来就该吃过期缓存，"
                             "这条不成立时下面那半段的说法要一起改" % got)
            for mod, where in self._entry_points():
                boot = ("import tempfile as _t, uuid as _u; "
                        "sys.dont_write_bytecode = True; "
                        "sys.pycache_prefix = str(pathlib.Path(_t.gettempdir()) / 'sb-t' / _u.uuid4().hex)")
                self.assertEqual(self._spawn(self.LOAD_BY_PATH, PROBE, bootstrap=boot), "from-B",
                                 "设了纪律后仍读到旧字节码：%s" % mod)
        finally:
            self._cleanup()

    def test_entry_scripts_actually_apply_the_discipline(self):
        """不问源码里有没有那两行，只问"import 完这个入口之后，解释器现在的值是什么"。

        用行为而不是 grep 来验：源码里写着、但被 sitecustomize/`-E` 改回去的话，
        这里照样会红。
        """
        for mod, where in self._entry_points():
            code = ("import sys, tempfile\n"
                    "sys.path.insert(0, sys.argv[1])\n"
                    "import " + mod + "\n"
                    "p = sys.pycache_prefix or ''\n"
                    "print('|'.join([str(sys.dont_write_bytecode),\n"
                    "               str(p.startswith(tempfile.gettempdir())),\n"
                    "               str(not p.startswith(sys.argv[2])),\n"
                    "               str(p != '')]))\n")
            d = ROOT if where == "." else ROOT / where
            pr = subprocess.run([sys.executable, "-c", code, str(d), str(ROOT)],
                                cwd=str(ROOT), capture_output=True, text=True,
                                encoding="utf-8", errors="replace",
                                env={k: v for k, v in os.environ.items()
                                     if k not in ("PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE")})
            self.assertEqual(pr.returncode, 0, "%s 导入失败：%s" % (mod, pr.stderr[-300:]))
            self.assertEqual(pr.stdout.strip(), "True|True|True|True",
                             "入口 %s 被 import 之后纪律没生效（实际 %r；期望依次是 "
                             "不写字节码 | 前缀在系统临时目录 | 前缀不在仓库内 | 前缀非空）—— "
                             "它跑出来的数字要降级为未验证" % (mod, pr.stdout.strip()))

    def test_prefix_is_unique_per_run_so_a_previous_run_cannot_be_read(self):
        """前缀必须是每次运行唯一的：固定路径的话，上一次 compileall 写的缓存
        就成了下一次的"相符"缓存 —— 那正是我们要防的那一类，只是换了个地方。"""
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import _preflight; "
                "print(sys.pycache_prefix)")
        seen = set()
        for _ in range(2):
            pr = subprocess.run([sys.executable, "-c", code, str(ROOT / "console")],
                                cwd=str(ROOT), capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
            self.assertEqual(pr.returncode, 0, pr.stderr[-300:])
            seen.add(pr.stdout.strip())
        self.assertEqual(len(seen), 2, "两次运行拿到同一个缓存前缀：%s" % seen)

    def test_compileall_does_not_litter_the_repo(self):
        """release_check 第一件事是 compileall，它会显式写缓存 —— 不许写在仓库里。

        这条是我自己踩出来的回归：上一版把前缀指到 ROOT/.pyc-offstage，一次
        release_check 就在仓库里长出 77 个 .pyc（git 还被 "Filename too long" 噎住）。
        只断言"不写字节码"挡不住 compileall，必须真的跑一遍再数。
        """
        before = {str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()}
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import compileall, release_check;"
                "print(compileall.compile_dir(sys.argv[2], quiet=1, maxlevels=2))")
        pr = subprocess.run([sys.executable, "-c", code, str(ROOT), str(ROOT / "console")],
                            cwd=str(ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
        self.assertEqual(pr.returncode, 0, pr.stderr[-400:])
        after = {str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()}
        new_files = sorted(f for f in (after - before) if not f.endswith(".pyc")
                           or "__pycache__" not in f)
        self.assertEqual(new_files, [],
                         "跑了一次带纪律的 compileall，仓库里多出这些文件：%s —— "
                         "缓存前缀必须留在仓库外" % new_files[:8])


if __name__ == "__main__":
    unittest.main()
