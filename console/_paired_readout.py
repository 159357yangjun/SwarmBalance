# -*- coding: utf-8 -*-
r"""配对实验的**可判性**读数：把"能不能下结论"这件事本身量化（只进报告行，不进退出码）。

为什么要有它：`paired_ga_vs_greedy.csv` 印的是胜/平/负与平均改进，是**描述性**的
（`build_conclusion_package.py:152` 自己就写了"不代表统计显著性"），但纸面上那句免责声明
没有任何东西保证它被兑现 —— n=5、标准差大于均值时，那三列胜负读起来就像结论。
本轮实测的形状就是这一类：greedy vs GA 逐 seed 时延 3:2，差值 mean=+1.098、sd=5.612、
**五个差值不同号** ⇒ 单种子噪声主导，任何"A 优于 B"的说法都撑不住。

三条量（全部现算，不抄 CSV）：
- `sign_wins/ties/losses`：同 seed 配对后按方向判优的计数；
- `exact_p_two_sided`：**穷举** 2^n 符号置换的双侧精确 p（n≤5 全枚举，不是近似）；
  n 再大要换成动态规划，不许悄悄截断；
- `smallest_possible_p = 2·C(n,⌊n/2⌋)/2^n`：**这组样本在数学上能达到的最小 p**。
  它是这条门真正的用处：如果连最小可得 p 都 > α，那么无论数据怎么长都不会显著 ⇒
  "这个实验设计回答不了这个问题"，而不是"这次没测出显著"。

短码（GBK 控制台下中文会变 ??????，判定信息一律带 ASCII 码）：
    [PAIRED_UNJUDGEABLE]  最小可得 p > α —— 当前重复次数在设计上就不可判
    [PAIRED_NOT_SIGNIF]   最小可得 p ≤ α，但本次精确 p > α —— 可判，只是没测出来
    [PAIRED_SIGNIF]       精确 p ≤ α —— 才允许写方向性结论
    [PAIRED_NO_DATA]      没有 algorithm_comparison 配对行 / 两侧 seed 不齐
默认读最新一次 `conclusion_*` 实验目录；`--dir` 指定，`--metric` 加测指标。
退出码恒为 0（这是读数不是门）—— 除非 `--gate`：那时 [PAIRED_UNJUDGEABLE] 会返回 1，
用来钉"结项包里的配对表必须在可判的设计下生成"。
"""
from __future__ import annotations

import argparse
import csv
import io
import itertools
import json
import math
import statistics as ST
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP_ROOT = ROOT / "results" / "experiments"
BASE, CAND = "greedy", "ga"
# 方向必须与 experiments/reporting.py 同一把尺子：这里只做引用，不抄第二份名单。
# 但 reporting.py 会拉起整条内核依赖（numpy/shapely/osmnx）—— 一个只读 CSV 的判读工具
# 不该因为环境缺包就起不来，所以按文件路径单独取那三个集合；取不到就停下，绝不猜。
_REPORTING_SRC = ROOT / "experiments" / "reporting.py"


def _direction_sets():
    import ast

    tree = ast.parse(_REPORTING_SRC.read_text(encoding="utf-8"))
    got = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], "id", "")
            if name in ("HIGHER_IS_BETTER", "LOWER_IS_BETTER", "DIRECTION_AMBIGUOUS"):
                try:
                    got[name] = set(ast.literal_eval(node.value))
                except ValueError:
                    raise AssertionError("[PAIRED_PARSE] %s 不是字面量集合，判据无法成立" % name)
    missing = {"HIGHER_IS_BETTER", "LOWER_IS_BETTER", "DIRECTION_AMBIGUOUS"} - set(got)
    if missing:
        raise AssertionError("[PAIRED_PARSE] reporting.py 里解析不到 %s —— 它改名了？"
                             % sorted(missing))
    return got


_HI = _direction_sets()["HIGHER_IS_BETTER"]
_LO = _direction_sets()["LOWER_IS_BETTER"]
_AMB = _direction_sets()["DIRECTION_AMBIGUOUS"]

ALPHA = 0.05


def latest_experiment() -> Path | None:
    ds = sorted(p for p in EXP_ROOT.glob("conclusion_*") if p.is_dir())
    return ds[-1] if ds else None


def per_seed(raw_path: Path):
    """-> {算法: {seed: 行}}，只取 algorithm_comparison 且成功的行。"""
    out = {}
    with io.open(raw_path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("实验") != "algorithm_comparison" or r.get("成功") != "True":
                continue
            out.setdefault(r["算法key"], {})[str(r["Seed"])] = r
    return out


def direction(metric):
    if metric in _AMB:
        return None
    if metric in _HI:
        return +1
    if metric in _LO:
        return -1
    return None


def exact_sign_test(deltas):
    """穷举 2^n 符号置换的双侧精确 p。n>8 直接拒绝：不许用近似冒充精确。"""
    n = len(deltas)
    if n > 8:
        raise AssertionError("[PAIRED_N_TOO_BIG] n=%d 需要穷举 2^%d 个置换，本工具不做近似" % (n, n))
    obs = abs(sum(deltas))
    tot = 0
    ge = 0
    for signs in itertools.product((1, -1), repeat=n):
        tot += 1
        if abs(sum(s * d for s, d in zip(signs, deltas))) >= obs - 1e-12:
            ge += 1
    return ge / tot, tot


def smallest_p(n):
    """这组样本在数学上能达到的最小双侧 p（全部同号、且无零差值时）。

    公式不是 `2·C(n,n/2)/2^n` —— 那个在偶数 n 上会**高估**：n=2 全同号时 |±1∓1| 的分布里
    只有 {0,2} 两档，`P(|T|>=2)=2/4=0.5`，而 `2·C(2,1)/4=1.0`。所以直接按统计量分布算：
    枚举全部 2^n 个符号置换取 `|sum(s_i·d_i)|`，数出 >= 观测值（=全同号）的比例。
    与 exact_sign_test 同一条路，因此两者天然一致（不一致会被常驻用例抓）。
    """
    obs = float(n)                       # 全同号时 |sum| 最大 = n
    hits = tot = 0
    for signs in itertools.product((1, -1), repeat=n):
        tot += 1
        if abs(sum(signs)) >= obs - 1e-12:
            hits += 1
    return hits / tot


def analyse(exp_dir: Path, metric: str):
    raw = exp_dir / "raw_runs.csv"
    if not raw.is_file():
        print("[PAIRED_NO_DATA] 缺 %s" % raw)
        return None
    by = per_seed(raw)
    if BASE not in by or CAND not in by:
        print("[PAIRED_NO_DATA] 算法两侧不齐：%s" % sorted(by))
        return None
    seeds = sorted(set(by[BASE]) & set(by[CAND]))
    only_b, only_c = sorted(set(by[BASE]) - set(seeds)), sorted(set(by[CAND]) - set(seeds))
    if not seeds:
        print("[PAIRED_NO_DATA] 没有共同 seed")
        return None
    sign = direction(metric)
    if sign is None:
        vals = {k: [float(by[k][s][metric]) for s in seeds] for k in (BASE, CAND)}
        sp = smallest_p(len(seeds))
        print("[PAIRED_NO_DIRECTION] %s 在 reporting 里没有登记方向 ⇒ 不产出胜负与 p 值；"
              "只印两侧均值。顺带一条与方向无关的事实：n=%d 时**任何**双侧符号检验的最小可得 p"
              " = %.4f > alpha=%.2f ⇒ 这个重复次数在设计上就给不出显著性。"
              % (metric, len(seeds), sp, ALPHA))
        print("[PAIRED_RAW] %s n=%d base_mean=%.6f cand_mean=%.6f sd_base=%.6f sd_cand=%.6f"
              % (metric, len(seeds), ST.mean(vals[BASE]), ST.mean(vals[CAND]),
                 ST.stdev(vals[BASE]), ST.stdev(vals[CAND])))
        return {"metric": metric, "n": len(seeds), "p": float("nan"), "smallest_p": sp,
                "win": 0, "loss": 0, "tie": 0,
                "code": "[PAIRED_UNJUDGEABLE]" if sp > ALPHA else "[PAIRED_NO_DIRECTION]"}
    try:
        pairs = [(float(by[CAND][s][metric]) - float(by[BASE][s][metric])) * sign for s in seeds]
    except KeyError as exc:
        print("[PAIRED_NO_DATA] 指标列缺失：%s" % exc)
        return None
    wins = sum(1 for d in pairs if d > 0)
    losses = sum(1 for d in pairs if d < 0)
    ties = len(pairs) - wins - losses
    p, perms = exact_sign_test(pairs)
    sp = smallest_p(len(pairs))
    same_sign = len({d > 0 for d in pairs}) == 1 and 0 not in [d > 0 for d in pairs]
    code = ("[PAIRED_SIGNIF]" if p <= ALPHA
            else ("[PAIRED_UNJUDGEABLE]" if sp > ALPHA else "[PAIRED_NOT_SIGNIF]"))
    print("%s dir=%s n=%d seeds=%s only_base=%d only_cand=%d perms=%d"
          % (code, "+" if sign > 0 else "-", len(pairs), ",".join(seeds),
             len(only_b), len(only_c), perms))
    print("[PAIRED_METRIC] %s base=%s cand=%s" % (metric, BASE, CAND))
    for s, d in zip(seeds, pairs):
        print("  [SEED] %s base=%.6f cand=%.6f signed_delta=%+.6f"
              % (s, float(by[BASE][s][metric]), float(by[CAND][s][metric]), d))
    print("[PAIRED_COUNTS] win=%d tie=%d loss=%d" % (wins, ties, losses))
    print("[PAIRED_EFFECT] mean_signed_delta=%+.6f sd=%.6f cv=%s"
          % (ST.mean(pairs), ST.stdev(pairs) if len(pairs) > 1 else float("nan"),
             "%.2f" % (ST.stdev(pairs) / abs(ST.mean(pairs)))
             if len(pairs) > 1 and ST.mean(pairs) else "n/a"))
    print("[PAIRED_P] exact_two_sided=%.4f smallest_possible=%.4f alpha=%.2f 同号=%s"
          % (p, sp, ALPHA, same_sign))
    print("[PAIRED_READ] 若 %s 的最小可得 p 已 > %.2f，则此重复次数在设计上不可能显著 —— "
          "要的是加 seed，不是换说法" % (metric, ALPHA))
    return {"metric": metric, "n": len(pairs), "p": p, "smallest_p": sp,
            "win": wins, "loss": losses, "tie": ties, "code": code}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default="", help="实验目录；默认取最新 conclusion_*")
    ap.add_argument("--metric", action="append", default=[], help="可重复；默认 超时率 + 平均时延")
    ap.add_argument("--gate", action="store_true",
                    help="把 [PAIRED_UNJUDGEABLE] 当失败（用于钉'配对表须在可判设计下生成'）")
    args = ap.parse_args(list(sys.argv[1:] if argv is None else argv))

    d = Path(args.dir) if args.dir else latest_experiment()
    if not d or not d.is_dir():
        print("[PAIRED_NO_DATA] 找不到实验目录（--dir 或 results/experiments/conclusion_*）")
        return 2
    print("[PAIRED_SOURCE] %s" % d.relative_to(ROOT).as_posix())
    metrics = args.metric or ["超时率", "平均时延"]
    res = [x for x in (analyse(d, m) for m in metrics) if x]
    if not res:
        return 0 if not args.gate else 2
    unjudgeable = [r for r in res if r["code"] == "[PAIRED_UNJUDGEABLE]"]
    print("[PAIRED_SUMMARY] metrics=%d unjudgeable=%d significant=%d alpha=%.2f"
          % (len(res), len(unjudgeable),
             sum(1 for r in res if r["code"] == "[PAIRED_SIGNIF]"), ALPHA))
    if args.gate and unjudgeable:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
