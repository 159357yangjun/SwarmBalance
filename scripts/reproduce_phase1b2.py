# -*- coding: utf-8 -*-
"""Phase 1B-2 结论的一键复现（本地运行包入口）。

    python scripts/reproduce_phase1b2.py            # 完整 n=8：32 cells
    python scripts/reproduce_phase1b2.py --quick    # 单 seed 40901：4 cells（快速自检）

它做四件事，全部走生产代码路径，不 import 任何"演示专用"的假数据：
  1) 环境预检（解释器/依赖），缺依赖就明确报错并给出该用的绝对路径 —— 不让评审把
     "我用错解释器"读成"仿真坏了"；
  2) 跑 C-1/C-2 × seeds × {w=0.0, w=1.2} × euclid 面（被切变量只有权重）；
  3) 现算超时率/完成数对比表 + 穷举符号检验精确 p（复用 console/_paired_readout.py，
     与常驻门同一把尺子，不在这里另写一份统计实现）；
  4) 打印已知问题清单（含 PSO 红门），并把日志落到 results/adhoc/（已 gitignore）。

为什么默认 n=8 而不是用户提到的"n=8 里的 40901 一个 seed"：单个 seed 上符号检验没有分母
（n=1 的最小可达 p = 1.0），报出来的 p 值会是装饰。所以完整模式跑满 8 个 seed，
`--quick` 只用于验证链路通不通、显式声明不出统计结论。
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "console"))
sys.path.insert(0, str(REPO))

FIXTURES = ("C1", "C2")
WEIGHTS = (0.0, 1.2)          # 基线 vs README 里演示的那一档
FULL_SEEDS = tuple(range(40901, 40909))
QUICK_SEEDS = (40901,)
LOG_DIR = REPO / "results" / "adhoc"


def preflight() -> pathlib.Path:
    """解释器与依赖检查；返回可用的项目解释器绝对路径。"""
    try:
        import _preflight as PF
        py = PF.venv_python()
    except Exception:
        py = None
    if py is None:
        for cand in (REPO / ".venv310" / "Scripts" / "python.exe",
                      REPO.parent / ".venv310" / "Scripts" / "python.exe"):
            if cand.is_file():
                py = cand
                break
    if py is None:
        raise SystemExit("[ENV] 找不到 .venv310。请在仓库根或其上一级建 venv 后装 requirements，"
                         "再重跑本脚本。（这是环境问题，不是仿真缺陷）")
    probe = subprocess.run([str(py), "-X", "utf8", "-c",
                            "import shapely,numpy;print('OK')"],
                           cwd=str(REPO / "frontend"), capture_output=True, text=True, timeout=300)
    if "OK" not in probe.stdout:
        raise SystemExit("[ENV] 解释器 %s 缺依赖：\n%s" % (py, (probe.stdout + probe.stderr)[-500:]))
    print("[ENV] 解释器 = %s" % py)
    return pathlib.Path(py)


def run_cells(py: pathlib.Path, seeds, out_dir: pathlib.Path):
    """逐格跑 worker，返回 {(fx, seed, weight): metrics}。只走 euclid 面。"""
    sys.path.insert(0, str(REPO))
    from console import phase1b1_experiment as H
    got = {}
    for fx in FIXTURES:
        for sd in seeds:
            for w in WEIGHTS:
                t0 = time.perf_counter()
                res = H.run_cell(fx, sd, "euclidean", "greedy", out_dir, reach_weight=w)
                m = res["metrics"]
                got[(fx, sd, w)] = m
                print("   %-3s seed=%d w=%-4s 完成=%3d 超时率=%.4f 时延=%7.2f (%.1fs)"
                      % (fx, sd, w, int(m["完成任务数"]), m["超时率"], m["平均时延"],
                         time.perf_counter() - t0), flush=True)
    return got


def sign_table(got, seeds):
    """穷举符号检验（复用常驻门的同一实现），返回可打印行。"""
    import _paired_readout as PR
    lines = []
    for kpi, better, word in (("超时率", -1, "越低越好"),
                              ("完成任务数", 1, "越高越好"),
                              ("平均时延", -1, "越低越好")):
        for fx in FIXTURES:
            deltas = []
            for sd in seeds:
                base = got.get((fx, sd, 0.0), {}).get(kpi)
                alt = got.get((fx, sd, 1.2), {}).get(kpi)
                if base is None or alt is None:
                    return None, "读数不全，拒绝出统计结论"
                deltas.append((float(alt) - float(base)) * better)
            nz = [d for d in deltas if abs(d) > 1e-12]
            wins = sum(1 for d in deltas if d > 0)
            losses = sum(1 for d in deltas if d < 0)
            ties = len(deltas) - len(nz)
            if not nz:
                p, perms, smallest = 1.0, 0, 1.0
            else:
                p, perms = PR.exact_sign_test(nz)
                smallest = PR.smallest_p(len(nz))
            lines.append("| %s | %s | %s | %d | %d | %d | %.4f | %d | %.4f |"
                         % (kpi, word, fx, wins, losses, ties, p, len(nz), smallest))
    return lines, None


def main(argv):
    quick = "--quick" in argv
    seeds = QUICK_SEEDS if quick else FULL_SEEDS
    py = preflight()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = LOG_DIR / ("repro1b2_%s" % time.strftime("%Y%m%d-%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)
    print("\n[计划] fixtures=%s seeds=%s weights=%s provider=euclidean algorithm=greedy ⇒ %d cells"
          % (list(FIXTURES), list(seeds), list(WEIGHTS),
             len(FIXTURES) * len(seeds) * len(WEIGHTS)))
    if quick:
        print("[注意] --quick 只有 1 个 seed ⇒ 符号检验没有分母，本次输出**不构成统计结论**，"
              "仅验证链路可跑。要复现文档里的 p 值请用不带参数的完整模式。")
    got = run_cells(py, seeds, out_dir)

    L = ["", "=" * 78,
         "Phase 1B-2 复现结果（约束式履约保护罚分 W·min(0, slack_full/300)）",
         "配对方式：同 fixture、同 seed、同 provider(euclidean)、同算法(greedy)，唯一被切变量是权重",
         "=" * 78]
    L += ["", "## per-seed 对照表", "",
          "| fixture | seed | 超时率 w=0.0 | 超时率 w=1.2 | Δ | 完成数 w=0.0 | w=1.2 | Δ |",
          "|---|---|---|---|---|---|---|---|"]
    for fx in FIXTURES:
        for sd in seeds:
            b, a = got[(fx, sd, 0.0)], got[(fx, sd, 1.2)]
            L.append("| %s | %d | %.4f | %.4f | %+.4f | %d | %d | %d |"
                     % (fx, sd, b["超时率"], a["超时率"], a["超时率"] - b["超时率"],
                        int(b["完成任务数"]), int(a["完成任务数"]),
                        int(a["完成任务数"] - b["完成任务数"])))
    rows, err = sign_table(got, seeds)
    n_seeds = len(set(s for (_f, s, _w) in got))
    if n_seeds < 2:
        # 只有 1 个 seed 时不印表头：空表看起来像"算了但没结果"，会被读成检验失败而非样本不足。
        L += ["", "## 符号检验：本次跳过", "",
              "单 seed 没有分母（n=1 的最小可达 p = 1.0），任何 p 值都是装饰。",
              "要复现文档里的 p=0.0078，请去掉 --quick 跑完整 n=8。"]
    else:
        L += ["", "## 符号检验（穷举 2^n 双侧精确 p，非近似）", ""]
        if err:
            L.append("（未出统计结论：%s）" % err)
    if rows and n_seeds >= 2:
        L += ["| KPI | 方向 | fixture | 赞成 w=1.2 | 反对 | 平 | 精确 p | 非零 n | 该 n 最小可达 p |",
              "|---|---|---|---|---|---|---|---|---|"] + rows
        L += ["", "判据：**≥6/8 同号才算结论成立**（用户在 1B-2 拍板时给定）。",
              "口径提醒：这一层买的是履约（超时率、时延下降），付的是吞吐（完成任务数下降）。",
              "**两半必须一起报**；只讲超时率等于把代价藏起来。"]
    L += ["", "## 已知问题（不影响本层结论）", "",
          "- **PSO 红门**：`console/test_speed_fallback_gate.py::test_g2_...` 报 "
          "`[pso][NO_DENOMINATOR]`（PSO 一步都没进 optimize()）。属 Phase 0 未完项，"
          "已用基线复现证明先于 Phase 1B-* 改动 ⇒ **不影响 Greedy 层结论**，但在它闭合前"
          "不得对外宣称「四算法对比」。",
          "- 设备参数（耗电系数、换电 180 s、SLA 420/24）是**无来源情景参数**，见 "
          "`docs/数据来源与可追溯性登记表.md`；因此本实验证明的是"
          "「在该 SLA 设定下调度行为如此」，不是真实运营数字。",
          "- 默认权重仍是 0.0 ⇒ 上面 w=1.2 的行为在生产配置里是关闭的。",
          "", "日志与临时产物：%s（在 results/adhoc/ 下，已被 .gitignore 忽略）" % out_dir]
    text = "\n".join(L)
    print(text)
    log = LOG_DIR / "reproduce_phase1b2.log"
    log.write_text(text, encoding="utf-8")
    shutil_cleanup(out_dir)
    print("\n[log] %s" % log)
    return 0


def shutil_cleanup(out_dir: pathlib.Path) -> None:
    """清掉本次的临时 config/worker JSON；日志单独留在 adhoc 里供翻查。"""
    try:
        for f in sorted(out_dir.glob("*")):
            f.unlink(missing_ok=True)
        out_dir.rmdir()
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
