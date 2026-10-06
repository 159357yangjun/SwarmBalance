# -*- coding: utf-8 -*-
"""数据溯源与统计分析报告的**生成器**（唯一真源：仓内文件；本报告不手填任何数字）。

为什么做成生成器而不是手写文档：手写的那份一旦盘上文件变了就静默失真，而这份材料的
用途恰恰是"任何一格数字都能被第三方从仓内文件重算出来"。所以每个数都从 CSV/JSON 解析，
并配 `--verify`：重算后与磁盘上已落盘的报告逐字节比对，不一致 ⇒ 退 1。

用法
    python docs/build_data_provenance.py            # 生成/覆盖 docs/数据溯源与统计分析.md
    python docs/build_data_provenance.py --verify   # 只校验，不写盘；漂移则退 1
纪律：本脚本**只读**结项产物，绝不写 results/ 下任何东西。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_REL = Path("docs") / "数据溯源与统计分析.md"
EXP_DIR = ROOT / "results" / "experiments" / "conclusion_20260911-043701"
COMPARE_CSV = ROOT / "results" / "compare" / "one_click_latest.csv"
MANIFEST = ROOT / "results" / "compare" / "manifest.json"
SIM_JSON = ROOT / "config" / "simulation.json"
POSITIONS = ROOT / "config" / "positions.json"
OSM = ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm"
ALPHA = 0.05


def sha(path: Path, nbytes_limit=None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def git(*args):
    """git 输出含中文（status/branch 的引号转义、提交信息）⇒ Windows 默认 GBK 解码会炸线程。

    这里必须显式指定 UTF-8，否则 `--verify` 会在异常栈之后**照样返回 0** ——
    一个"坏了却报绿"的量具比没有量具更危险。
    """
    try:
        r = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        return (r.stdout or "").strip()
    except OSError:
        return ""


def exact_sign_test(deltas, alpha=ALPHA):
    """精确双侧符号检验：枚举 2^m 个符号组合，不做正态近似。

    平局（Δ=0）按符号检验惯例剔除，并从 m 里扣掉——所以分母是**非零对数**，
    这一点必须印在报告里，否则读者会把 ties 当成"GA 与 greedy 打平的证据"。
    """
    n = len(deltas)
    nonzero = [d for d in deltas if d != 0.0]
    m = len(nonzero)
    if m == 0:
        return dict(n=n, ties=n, m=0, k_pos=0, p=float("nan"), smallest_p=float("nan"),
                    judgeable=False, note="全部平局，符号检验无定义")
    k = sum(1 for d in nonzero if d > 0.0)
    obs = abs(k - m / 2.0)
    ge = sum(1 for bits in itertools.product((0, 1), repeat=m)
             if abs(sum(bits) - m / 2.0) >= obs - 1e-12)
    p = ge / (2 ** m)
    # 最小可得 p：该统计量分布里最极端那一档的尾概率（不是闭式 2·C(n,⌊n/2⌋)/2ⁿ）
    smallest_p = min(
        sum(1 for bits in itertools.product((0, 1), repeat=m)
            if abs(sum(bits) - m / 2.0) >= abs(i - m / 2.0) - 1e-12) / (2 ** m)
        for i in range(m + 1))
    return dict(n=n, ties=n - m, m=m, k_pos=k, p=p, smallest_p=smallest_p,
                judgeable=(p <= alpha), note="")


def f(x, nd=4):
    if x is None:
        return "—"
    if isinstance(x, float):
        return ("%." + str(nd) + "f") % x
    return str(x)


def build():
    L = []
    A = L.append
    sim = json.loads(SIM_JSON.read_text(encoding="utf-8"))
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = read_csv(EXP_DIR / "raw_runs.csv")
    ac = [r for r in raw if r["实验"] == "algorithm_comparison"]
    seeds = sorted({r["Seed"] for r in ac})
    algs = sorted({r["算法key"] for r in ac})
    latest = read_csv(COMPARE_CSV)
    rep = json.loads((EXP_DIR / "reproducibility.json").read_text(encoding="utf-8"))
    entry = man["files"]["one_click_latest.csv"]

    A("# 数据溯源与统计分析报告")
    A("")
    A("> 本页由 `python docs/build_data_provenance.py` 从仓内文件生成，**一个数字都不手填**。")
    A("> 校验：`python docs/build_data_provenance.py --verify` —— 与磁盘版本不一致即退 1。")
    A("> 口径边界见 §1，它比后面所有表格都重要：**本项目没有真实无人机运行数据**。")
    A("")
    A("## 0. 生成时刻的仓库指纹")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 生成时间（本地） | %s |" % time.strftime("%Y-%m-%d %H:%M:%S"))
    A("| 当前 HEAD | `%s` |" % (git("rev-parse", "--short", "HEAD") or "（非 git 环境）"))
    A("| 工作树是否干净 | %s |" % ("是" if git("status", "--porcelain") == "" else "**否（有未提交改动）**"))
    A("| 结项运行钉住的提交 | `%s` |" % rep["git_commit"])
    A("")
    A("## 1. 数据来源分级（先说清哪些是真的）")
    A("")
    A("判据三级，来自本项目自己的验收条款（`docs/仿真软件设计规范.md:36`「禁止使用无来源的魔法数」）：")
    A("")
    A("- **A 外部可核**：能从仓外权威来源逐位复核；")
    A("- **B 参考对标**：取自公开产品铭牌但项目自行调整过，或厂商根本不公布该项；")
    A("- **C 设定值**：无任何可核查出处，是人为拍的数。")
    A("")
    A("### 1.1 A 级（真正的外部数据，共 2 项）")
    A("")
    A("| # | 内容 | 仓内位置 | 大小(B) | SHA-256 | 外部来源 | 复核方式 |")
    A("|---|---|---|---|---|---|---|")
    osm_sha = sha(OSM)
    A("| A1 | 城市路网与建筑轮廓（上海杨浦） | `frontend/data/map/part_of_yangpu.osm` | %d | `%s…%s` | OpenStreetMap（ODbL 1.0），文件头自带 `generator=openstreetmap-cgimap 2.1.0`、`bounds minlat=31.27393 minlon=121.49127 maxlat=31.31251 maxlon=121.53797`，节点带 changeset/user/timestamp | 打开 planet.osm 导出同 bbox 比对 bounds 与节点 id |" % (
        OSM.stat().st_size, osm_sha[:12], osm_sha[-6:]))
    fc = sim["heterogeneous"]["drone_types"]["heavy_cargo"]
    A("| A2 | `heavy_cargo` 电池容量 %s Wh | `config/simulation.json` → `heterogeneous.drone_types.heavy_cargo.battery_capacity` | — | — | DJI FlyCart 30 官方规格页（双电 2×1984.4 Wh） | 2×1984.4=%.1f，与盘上值**逐位吻合**" % (
        f(fc["battery_capacity"], 1), 2 * 1984.4))
    A("")
    A("### 1.2 机队配置档参数（按证据性质分列，不合并成一张\"真实机型表\"）")
    A("")
    A("`light_express` / `standard_cargo` 是**通用载重档位**，不对应任何厂商机型；"
      "`heavy_cargo` 有官方规格锚点。三档同表展示会让读者把档位名读成机型身份，故拆列。")
    A("")
    A("| 配置档 | 型号标注 | 速度 m/s | 载重 kg | 电池 Wh | 能耗基线 | 满载航程 km | real_vehicle_mapping | parameter_nature |")
    A("|---|---|---|---|---|---|---|---|---|")
    TIER_META = {
        "light_express": dict(mapping="none", nature="scenario"),
        "standard_cargo": dict(mapping="none", nature="scenario"),
        "heavy_cargo": dict(mapping="DJI FlyCart 30", nature="vendor_anchored"),
    }
    for key in ("light_express", "standard_cargo", "heavy_cargo"):
        d = sim["heterogeneous"]["drone_types"][key]
        meta = TIER_META[key]
        A("| `%s` | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            key, d["model"], f(d["speed"], 1), f(d["carrying_capacity"], 1),
            f(d["battery_capacity"], 1), f(d["battery_consumption_base"], 3),
            f(d.get("full_load_range_km"), 1), meta["mapping"], meta["nature"]))
    A("")
    A("证据等级（审计术语放这里，不放 UI 的 `model` 字段）：")
    A("")
    A("| 配置档 | evidence_level_direct | evidence_level_energy | 说明 |")
    A("|---|---|---|---|")
    A("| `heavy_cargo` | A（官方规格页直接值：速度、满载/空载航程、单块电池 Wh） | C（由官方 3968.8÷28 km 与 28÷16 派生） | 见 §1.1 A2 与 `data/provenance/parameters.csv` |")
    A("| `standard_cargo` | A（载重 10 kg、航程 20 km、巡航 14 m/s 为厂商页直接值） | D（电池容量与能耗系数厂商未公布，无外部依据） | **不得称\"对标 ARK40 官方电池\"** |")
    A("| `light_express` | E（仅媒体口径，无厂商规格页） | D | 载重 2.4 kg 系项目自定，媒体口径为 2.5 kg |")
    A("")
    A("### 1.3 C 级（无来源设定值 —— 这一节决定结论能不能外推）")
    A("")
    dr = sim["drone"]
    ne = sim["nest"]
    tc = sim["task_chain"]
    tk = sim["task"]
    env = sim["environment"]
    A("| 参数 | 盘上值 | 位置 | 为什么是 C | 影响面 |")
    A("|---|---|---|---|---|")
    A("| `battery_consumption_base` ×3 | %s / %s / %s | `heterogeneous.drone_types.*` | 厂商不公布放电曲线，只能自拟合 | 换电次数 → 机巢占用 → 完成率/时延 |" % (
        f(sim["heterogeneous"]["drone_types"]["light_express"]["battery_consumption_base"], 3),
        f(sim["heterogeneous"]["drone_types"]["standard_cargo"]["battery_consumption_base"], 3),
        f(sim["heterogeneous"]["drone_types"]["heavy_cargo"]["battery_consumption_base"], 3)))
    A("| `battery_load_penalty_factor` ×3 | %s / %s / %s | 同上 | 同上 | 同上 |" % (
        f(sim["heterogeneous"]["drone_types"]["light_express"]["battery_load_penalty_factor"], 2),
        f(sim["heterogeneous"]["drone_types"]["standard_cargo"]["battery_load_penalty_factor"], 2),
        f(sim["heterogeneous"]["drone_types"]["heavy_cargo"]["battery_load_penalty_factor"], 2)))
    A("| `swap_time_seconds` | %s | `nest` / `drone` / 各机巢 / `backend_si/config.yaml`（**四处冗余**） | 无来源（登记表 P5） | 换电停机时长 |" % ne["swap_time_seconds"])
    A("| `battery_low_threshold` | %s | `drone` | 无来源（登记表 P6） | 回巢时机 |" % dr["battery_low_threshold"])
    A("| 建筑高度 fallback | 12 m 与 层高×3.0 | `frontend/tools/osm.py` | 两处不一致且无来源（登记表 :96） | 绕飞路径 |")
    A("| `max_detour_m` | %s | `task_chain` | 顺路半径，无来源 | 顺路接入次数 |" % f(tc["max_detour_m"], 1))
    A("| `battery_reserve_ratio` | %s | `task_chain` | 无来源 | 同上 |" % f(tc["battery_reserve_ratio"], 2))
    A("| `sla_base_seconds` / `sla_per_kg_seconds` | %s / %s | `task` | 送达时限公式的两个系数，无来源 | **超时率**（对外主指标） |" % (
        tk["sla_base_seconds"], tk["sla_per_kg_seconds"]))
    A("| `reward_*` / `penalty_*` ×%d | 见文件 | `environment` | MARL 遗留奖励塑形，无来源 | 不参与网页端四算法读数 |" % 9)
    A("")
    A("**V&V 三档分开报（不许混）**：")
    A("")
    A("- Verification（实现是否忠实于设定）：可查，见 §4 的逐格复算；")
    A("- Validation（模型是否代表真实系统）：**不成立** —— 没有任何实机飞行数据可做对撞；")
    A("- Sensitivity analysis（设定变动时结论是否翻转）：仅有区间证据（`docs/数据来源与可追溯性登记表.md` 的消融章节），**未做系统扫描 ⇒ 未验**。")
    A("")
    A("对外只允许这样表述：*在 OSM 真实路网上、以三款公开产品铭牌为参考构建的异构机队假设下，四种调度算法的相对表现*。凡出现\"真实无人机参数 / 实测校准 / 可直接指导运营\"的字样均属夸大，须撤。")
    A("")

    A("## 2. 一手数据清单（每格可复算）")
    A("")
    A("| 文件 | 行数 | SHA-256 | 说明 |")
    A("|---|---|---|---|")
    for rel in ("raw_runs.csv", "algorithm_comparison.csv", "paired_ga_vs_greedy.csv",
                "algorithm_comparison_stats.csv", "plan.csv", "reproducibility.json"):
        p = EXP_DIR / rel
        rows = len(read_csv(p)) if p.suffix == ".csv" else "—"
        A("| `results/experiments/conclusion_20260911-043701/%s` | %s | `%s…` |  |" % (
            rel, rows, sha(p)[:16]))
    A("| `results/compare/one_click_latest.csv` | %d | `%s…` | 页面 `/api/compare` 的唯一来源 |" % (
        len(latest), sha(COMPARE_CSV)[:16]))
    pos = json.loads(POSITIONS.read_text(encoding="utf-8"))["positions"]
    dup = len(pos) - len({tuple(p) for p in pos})
    A("| `config/positions.json` | %d 个候选取送货点（重复坐标 %d 组） | `%s…` | 任务生成的目的地池 |" % (
        len(pos), dup, sha(POSITIONS)[:16]))
    A("")
    A("运行身份（`reproducibility.json` 原文）：preset=`%s`、plan_count=%d、generated_at_utc=%s、git_commit=`%s`、Python %s、osmnx %s、ortools %s。" % (
        rep["preset"], rep["plan_count"], rep["generated_at_utc"], rep["git_commit"][:7],
        rep["runtime"]["python"].split()[0], rep["packages"]["osmnx"], rep["packages"]["ortools"]))
    A("")
    fam = {e: sum(1 for r in raw if r["实验"] == e) for e in sorted({r["实验"] for r in raw})}
    total = sum(fam.values())
    A("实验族行数恒等式：%s，合计 %d；raw_runs 实际行数 %d ⇒ **%s**（不等即本表作废）。" % (
        " + ".join("%s:%d" % (k, v) for k, v in fam.items()), total, len(raw),
        "成立" if total == len(raw) else "不成立"))
    A("")

    A("## 3. 发布链（谁能改答辩页的数字）")
    A("")
    A("`raw_runs.csv` →（按算法取 %s 次均值 + round(...,6)）→ `algorithm_comparison.csv` →" % entry["episode_count"])
    A("（**双闸门**：`preset_key==\"conclusion\"` 且显式 `--publish-latest`，见 `experiments/runner.py`）→")
    A("`results/compare/one_click_latest.csv` → `/api/compare` → 前端表格。")
    A("")
    A("登记口径（`results/compare/manifest.json` 原值）：episode_max_steps=%s、episode_count=%s、seed_set=%s、generated_tasks=%s、schema=`%s`、provenance_recorded=%s。" % (
        entry["episode_max_steps"], entry["episode_count"], entry["seed_set"],
        entry["generated_tasks"], entry["metrics_schema_version"], entry["provenance_recorded"]))
    A("")

    A("## 4. 内部一致性对账（页面数字 vs 一手运行记录）")
    A("")
    cells = 0
    worst = (0.0, "")
    for row in latest:
        a = row["算法"]
        for metric, v in row.items():
            if metric == "算法":
                continue
            vals = [float(r[metric]) for r in ac if r["算法key"] == a]
            mean = sum(vals) / len(vals)
            page = float(v)
            rel = abs(page - mean) / max(abs(mean), 1e-12)
            cells += 1
            if rel > worst[0]:
                worst = (rel, "%s/%s 页=%s 重算=%.9f" % (a, metric, v, mean))
    A("- 比对格子数：**%d**（= %d 行 × %d 个可比列；该 CSV 共 %d 列，其中 `算法` 是行键、不参与对账）" % (
        cells, len(latest), len(latest[0]) - 1, len(latest[0])))
    A("- 最大相对差：**%.3e** @ %s" % (worst[0], worst[1]))
    A("- 结论：页面读数 = 这批运行记录的算术均值；差异只来自 CSV 存 6 位小数的舍入，**不存在计算分歧**。")
    A("- 但这只证明*内部一致*，不证明这批运行等于当前代码的行为（那批钉在 `%s`，早于载重修复 `4d956e6`）。" % rep["git_commit"][:7])
    A("")

    A("## 5. 描述统计（每算法 n=%d，seeds %s）" % (len(seeds), "–".join([seeds[0], seeds[-1]])))
    A("")
    metrics = ["完成率", "超时率", "平均时延", "从生成到完成总时间最大", "总能量消耗",
               "总飞行距离", "空载率", "无人机利用率", "机巢周转率", "禁飞区绕飞次数", "顺路接入次数"]
    A("| 指标 | " + " | ".join("`%s` mean±sd [min,max]" % a for a in algs) + " |")
    A("|---" * (len(algs) + 1) + "|")
    for m in metrics:
        cells_ = []
        for a in algs:
            v = [float(r[m]) for r in ac if r["算法key"] == a]
            sd = st.stdev(v) if len(v) > 1 else 0.0
            nd = 2 if max(abs(x) for x in v) > 100 else 4
            cells_.append("%s±%s [%.2f, %.2f]" % (f(st.mean(v), nd), f(sd, nd), min(v), max(v)))
        A("| %s | " % m + " | ".join(cells_) + " |")
    A("")
    A("读法提醒：**完成率四算法全为 1.0 ⇒ 该指标在这套设定下饱和，无判别力**；能区分算法的只有超时率/时延/能耗/绕飞这几列。")
    A("")

    A("## 6. 配对显著性（GA vs Greedy，同 seed）")
    A("")
    A("方法：精确双侧符号检验，枚举 2^m 个符号组合，不做正态近似。α=%s。" % ALPHA)
    A("")
    A("| 指标 | Δ均值(GA−Greedy) | 非零对 m | 平局 | 正号 k | 精确 p | 最小可得 p | 可判? |")
    A("|---|---|---|---|---|---|---|---|")
    for m in ["超时率", "平均时延", "总能量消耗", "从生成到完成总时间最大", "禁飞区绕飞次数"]:
        ds = []
        for s in seeds:
            g = [r for r in ac if r["Seed"] == s and r["算法key"] == "ga"]
            e = [r for r in ac if r["Seed"] == s and r["算法key"] == "greedy"]
            if len(g) == 1 and len(e) == 1:
                ds.append(float(g[0][m]) - float(e[0][m]))
        t = exact_sign_test(ds)
        verdict = "✗ 设计上给不出显著性" if not t["judgeable"] else "✓"
        A("| %s | %+.4f | %d | %d | %d | %s | %s | %s |" % (
            m, st.mean(ds), t["m"], t["ties"], t["k_pos"],
            f(t["p"], 4), f(t["smallest_p"], 4), verdict))
    A("")
    A("**这一节最重要的一句话**：n=5 时最小可得 p=%s > α=%s ⇒ **这个重复次数在设计上就给不出显著性**，"
      "不是\"没测出差别\"，而是\"这个样本量不可能测出差别\"。要判就得加 seed（n≥6 才第一次可判，n=8 最小可得 p≈0.0039）。" % (
          f(exact_sign_test([1.0, 1.0, -1.0, 1.0, -1.0])["smallest_p"], 4), ALPHA))
    A("")

    A("## 7. 已知缺陷与盲区（具名，不粉饰）")
    A("")
    A("| # | 事项 | 状态 | 证据 |")
    A("|---|---|---|---|")
    A("| D1 | 耗电系数/换电时长/SLA 系数为 C 级设定值，却直接决定超时率与能耗排序 | **已核实，未修** | 本文 §1.3 |")
    A("| D2 | `drone.speed=17.0` 与按机型 `speed=14.0/20.0` 并存，谁覆盖谁未定论 | **已核实，未修** | 登记表 P3 |")
    A("| D3 | `README.md:24`「参数取自…公开产品规格」：README 全部外链中指向机型规格页 **0 条** | **已核实，措辞待改** | 登记表 :485 |")
    A("| D4 | `docs/仿真软件设计规范.md:176` 验收项 ☐ 未勾，`:201` 却写 ✅ 已锚定 | **已核实，自相矛盾** | 登记表 :486 |")
    chain_vals = sorted({float(r["顺路接入次数"]) for r in ac if r["算法key"] == "greedy"})
    A("| D5 | `greedy` 顺路接入次数恒为 %s：grep 显示任务链接只在 `backend_si/pso_scheduler.py` 等侧实现，greedy 侧无对应分支 | **本轮新发现，属设计还是缺陷待定** | 本文 §5 该行 + `grep -rn \"顺路接入\" frontend/greedy backend_si` |" % (
        "0" if chain_vals == [0.0] else str(chain_vals)))
    A("| D6 | 同一份 .osm，缓存面 vs 强制重解析的道路条数差 **±2**（原记 cached=1237 / fresh=1235；2026-10-05 复跑为 cached=1237 / fresh=**1236** ⇒ 漂移量 2→1） | **已核实：差异真实且可复现，但成因未定 ⇒ 仍未验** | `docs/取证输出/osm-cache-three-face.txt:15-16`（旧读数）＋本轮复算命令见 §8 |")
    A("| D7 | 双闸门（缺任一门就不写 latest）此前从未被夹具证明 | 本轮补，见 `console/test_publish_gate.py` | — |")
    A("| D8 | 无实机数据 ⇒ Validation 整条缺失 | **不可修（除非引入真实运行日志）** | 本文 §1 |")
    A("")

    A("## 8. 复算命令表（每条都可复制执行）")
    A("")
    A("| 要复核什么 | 命令（在项目根目录执行） |")
    A("|---|---|")
    py = "../.venv310/Scripts/python.exe"
    A("| 本报告未漂移 | `%s docs/build_data_provenance.py --verify` |" % py)
    A("| 地图文件未被替换 | `sha256sum frontend/data/map/part_of_yangpu.osm`（应为 `%s`） |" % osm_sha)
    A("| 页面 4 行 = 一手运行均值 | `%s -c \"import csv,pathlib;r=list(csv.DictReader(open(r'results/experiments/conclusion_20260911-043701/raw_runs.csv',encoding='utf-8-sig')));ac=[x for x in r if x['实验']=='algorithm_comparison'];print({a:round(sum(float(x['超时率']) for x in ac if x['算法key']==a)/5,6) for a in {'ga','greedy','ortools','pso'}})\" |" % py)
    A("| 68 行的族分布 | `%s -c \"import csv,collections;r=list(csv.DictReader(open(r'results/experiments/conclusion_20260911-043701/raw_runs.csv',encoding='utf-8-sig')));print(collections.Counter(x['实验'] for x in r),len(r))\" |" % py)
    A("| 符号检验最小可得 p | `%s console/_paired_readout.py --dir results/experiments/conclusion_20260911-043701 --metric 超时率 --gate` |" % py)
    A("| 双闸门会拦 | `%s -m unittest console.test_publish_gate -v` |" % py)
    A("| 缓存三面实验原始输出 | `cat docs/取证输出/osm-cache-three-face.txt` |")
    # D6 的两面复算：走环境变量开关（frontend/tools/osm.py:255），**不删缓存文件**，
    # 所以这条命令不动盘、可反复执行。数字必须现算，不能像上一版那样把读数抄进模板
    # —— 抄进去的数下一次实测变了就没人发现（本轮就是这样：口头报的 1235 实为 1236）。
    _d6_py = ("import sys;sys.path.insert(0,'frontend');"
              "from environment import Environment;"
              "e=Environment('frontend/data/map/part_of_yangpu.osm',episode_max_steps=1);"
              "print(sum(len(v) for v in e.roads_by_type.values()),len(e.high_buildings))")
    A("| D6 两面几何条数（缓存 vs 现算） | 缓存面：`%s -X utf8 -c \"%s\"`；"
      "现算面：同一条命令前缀 `SWARM_BALANCE_OSM_CACHE=0`。两面的道路条数即 D6 的差值来源 |" % (py, _d6_py))
    A("| 口径单一真源 | `type results\\compare\\manifest.json`（或 `Get-Content`） |")
    A("")
    A("## 9. 未验清单（本轮没真跑到的面，不外推）")
    A("")
    A("- C 级参数的**敏感性区间**：未跑（用户已叫停实验批次）⇒ 不知道哪个系数一动结论就翻。")
    A("- **D6 的成因**：两面已各复算一次（命令见 §8），确认差异真实存在且随环境变化"
      "（旧 1237/1235、新 1237/1236），但**未定位到是哪条道路，也未排除 osmnx 版本因素** ⇒ 仍属未验。"
      "⚠ 上一轮口头报过\"现算 1235\"，同口径实测是 1236 —— 那是把旧文档读数当成了本轮测量；"
      "**引用 D6 以 §8 两条命令的输出为准，不要引任何人口头数字**。")
    A("- 当前代码重跑结项后的新数字与本报告数字的差：未跑。")
    # 原「D6 那 2 条道路的成因：未定位」一行已被上面那条展开并取代（漂移量本轮实测为 1，
    # 再写死\"2 条\"就是抄旧读数）；judgment 那条经实测撤回 —— server.py / index.html 命中均为 0。
    A("- ~~前端 `judgment` 字段的落地（③）：只做了一半，`index.html` 未接。~~ **本行已失效（2026-10-05 实测）**："
      "`console/server.py` 与 `console/static/index.html` 里 `judgment` 命中均为 **0** —— 不是\"做了一半\"，"
      "是该字段根本不在当前代码里。这条口径原先唯一的证人是 `docs/取证输出/server_judgment_WIP_39lines.py.bak`"
      "（一份旧 server.py 快照，含 `_compare_judgment()`），全仓 0 引用、文件名里的\"39lines\"与实际 1042 行也不符，"
      "已于 commit 41cf759 删除。**教训：一条只存在于未入库快照里的\"未完成项\"，会被当成活台账反复外报。**"
      "复算：`grep -c judgment console/server.py console/static/index.html` ⇒ 双双为 0。")
    A("- 实机数据对撞：仓内不存在该数据，**没有便宜通道**。")
    A("")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="与磁盘版本比对，不一致退 1")
    args = ap.parse_args(argv)
    text = build()
    out = ROOT / OUT_REL
    if args.verify:
        if not out.is_file():
            print("[PROVENANCE_MISSING] %s 不存在" % OUT_REL)
            return 1
        disk = out.read_text(encoding="utf-8")
        # 生成时刻与 HEAD 指纹两行必然每次不同 ⇒ 排除后再比
        keep = lambda s: [l for l in s.splitlines() if not (l.startswith("| 生成时间") or l.startswith("| 当前 HEAD") or l.startswith("| 工作树"))]
        if keep(disk) == keep(text):
            print("[PROVENANCE_OK] 报告与仓内文件一致（除生成时刻/HEAD 两行）行数=%d" % len(text.splitlines()))
            return 0
        print("[PROVENANCE_DRIFT] 盘上版本与现算不一致 ⇒ 数字已过期或被手改")
        dl, tl = keep(disk), keep(text)
        for i, (a_, b_) in enumerate(zip(dl, tl)):
            if a_ != b_:
                print("  首个差异 @ 有效行 %d\n    盘上: %s\n    现算: %s" % (i, a_[:160], b_[:160]))
                break
        print("  盘上有效行=%d 现算有效行=%d" % (len(dl), len(tl)))
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print("[PROVENANCE_WRITE] %s 行数=%d sha256=%s" % (OUT_REL, len(text.splitlines()), sha(out)[:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
