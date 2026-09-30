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


if __name__ == "__main__":
    unittest.main()
