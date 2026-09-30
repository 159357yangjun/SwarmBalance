"""One-command release/defense verification for SwarmBalance.

It does not modify experiment data. The default mode validates the portable Web/demo
path and all lightweight tests. ``--strict`` additionally requires the official
Python 3.10 + full dependency preflight to pass.
"""
from __future__ import annotations

import argparse
import compileall
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Tuple

ROOT = Path(__file__).resolve().parent


def _run(cmd: List[str], *, cwd: Path = ROOT) -> Tuple[bool, str]:
    # Windows 上 text=True 会按父进程 locale（cp936）解码子进程输出，而子进程打印的是
    # UTF-8，reader 线程直接 UnicodeDecodeError 死掉、stdout 变 None —— 于是失败时
    # 下面那些 `if not ok and out` 拿不到任何诊断文本，闸门会"FAIL 但不说为什么"。
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True,
                          encoding="utf-8", errors="replace", env=env)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out.strip()


def _print_result(name: str, ok: bool, detail: str = "") -> None:
    mark = "OK" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" · {detail}" if detail else ""))


def _check_js() -> Tuple[bool, str]:
    node = shutil.which("node")
    if not node:
        return True, "未找到 node，跳过前端语法检查（非运行依赖）"
    html = (ROOT / "console" / "static" / "index.html").read_text(encoding="utf-8")
    blocks = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.S | re.I)
    inline = "\n".join(b for b in blocks if b.strip())
    with tempfile.TemporaryDirectory() as td:
        js = Path(td) / "index-inline.js"
        js.write_text(inline, encoding="utf-8")
        ok, out = _run([node, "--check", str(js)])
    return ok, out or f"{len(inline.encode('utf-8'))} bytes inline JS"


def main() -> None:
    parser = argparse.ArgumentParser(description="SwarmBalance 结项发布自检")
    parser.add_argument("--strict", action="store_true", help="要求官方 Python 3.10 + 完整依赖预检也通过")
    parser.add_argument("--skip-e2e", action="store_true", help="跳过真实本地 OSM + Environment 端到端自检")
    args = parser.parse_args()

    failures = 0

    ok = compileall.compile_dir(str(ROOT), quiet=1, maxlevels=10)
    _print_result("Python compileall", ok)
    failures += 0 if ok else 1

    ok, out = _run([sys.executable, "-m", "unittest", "discover", "-s", "console", "-p", "test_*.py"])
    _print_result("console 单元测试", ok, out.splitlines()[-1] if out else "")
    failures += 0 if ok else 1

    # skip 归因：`OK (skipped=12)` 会被读成"过了 12 条"，而它真正的意思是
    # "这 12 条在这台机器上根本没跑"。答辩机上这必须是显眼的、带包名与模块的一行行清单。
    try:
        sys.path.insert(0, str(ROOT / "console"))
        import _preflight
        info = _preflight.collect_skips()
        if info["skipped"]:
            print("[INFO] 本次不可跑的用例（不是通过，是没跑）：")
            print(_preflight.render_skips(info["skipped"]))
            print("       要换解释器就跑：python console/_preflight.py --skips")
    except Exception as exc:  # noqa: BLE001 - 归因失败不该让整个发布检查崩掉
        print("[WARN] skip 归因没能生成：%s: %s" % (type(exc).__name__, exc))
        failures += 1

    ok, out = _run([sys.executable, "-m", "unittest", "discover", "-s", "experiments", "-p", "test_*.py"])
    _print_result("experiments 单元测试", ok, out.splitlines()[-1] if out else "")
    failures += 0 if ok else 1

    # 文档引用的核对结果要**在绿的时候也看得见覆盖率**：
    # 只判"路径存在 + 行号不越界"的门，看不见"行号对但指向别处"那一类，
    # 所以这里印的是「扫到几条 / 其中几条带锚点」，而不是只印一个 OK。
    try:
        sys.path.insert(0, str(ROOT / "console"))
        import _citations
        rc = _citations.main(["--verify"])
        _print_result("文档 path:line 引用核对", rc == 0)
        failures += 0 if rc == 0 else 1
    except Exception as exc:  # noqa: BLE001 - 归因失败不该让整个发布检查崩掉
        print("[WARN] 引用门禁没能生成：%s: %s" % (type(exc).__name__, exc))
        failures += 1

    ok, out = _check_js()
    _print_result("Web inline JavaScript 语法", ok, out.splitlines()[-1] if out else "")
    failures += 0 if ok else 1

    for preset in ("quick", "conclusion"):
        ok, out = _run([sys.executable, "run_conclusion.py", "--preset", preset, "--dry-run"])
        _print_result(f"{preset} 实验计划 dry-run", ok)
        if not ok and out:
            print(out[-1500:])
        failures += 0 if ok else 1

    if not args.skip_e2e:
        ok, out = _run([sys.executable, "-m", "console.selfcheck", "--steps", "1"])
        detail = "真实本地 OSM + Environment + Greedy + 插单 + 快照"
        _print_result("便携 Web 端到端自检", ok, detail)
        if not ok and out:
            print(out[-2000:])
        failures += 0 if ok else 1

    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td) / "evidence.zip"
        ok, out = _run([sys.executable, "build_conclusion_package.py", "--allow-missing-experiment", "--output", str(pkg)])
        ok = ok and pkg.exists()
        _print_result("结项证据包构建", ok, pkg.name if ok else (out.splitlines()[-1] if out else ""))
        failures += 0 if ok else 1

    from console.preflight import run_checks
    strict = run_checks(portable=False)
    strict_ok = not strict["errors"]
    if args.strict:
        _print_result("官方完整环境预检", strict_ok)
        if not strict_ok:
            for msg in strict["errors"]:
                print("  -", msg)
        failures += 0 if strict_ok else 1
    else:
        label = "通过" if strict_ok else "当前机器非官方完整环境（不影响便携 Web 自检）"
        print(f"[INFO] 官方完整环境预检 · {label}")
        if not strict_ok:
            for msg in strict["errors"]:
                print("  -", msg)

    if failures:
        print(f"\n发布自检失败：{failures} 项未通过。")
        raise SystemExit(2)
    print("\n发布自检通过。正式结项实验前仍建议在 Python 3.10 完整环境再执行：python release_check.py --strict")


if __name__ == "__main__":
    main()
