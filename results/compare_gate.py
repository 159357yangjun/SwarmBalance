# -*- coding: utf-8 -*-
"""results/compare 的口径门禁：不可比的实验不许被并列进同一张对比表/同一张图。

## 为什么需要它（全部为本机实测，不是推测）

`results/compare/` 里七个 CSV 被两个入口当同一批数据用：
- `console/server.py:_CSV_FILES` → `/api/compare` → Web「算法对比」页
- `results/plot_compare_metrics.py:CSV_FILES` → 20 张图 + 3 份派生表（论文图就来自这条链）

两个入口都用 `drop_duplicates(算法, keep="last")`，但**文件清单不一样**（只有 server
带 `one_click_latest.csv`），于是同一批文件在两条链上选出的是**不同的行**：

    图侧:  greedy 2000步/60任务  pso 2000/60  ga 600/30  ortools 2000/60
    页侧:  四个算法全部来自 one_click_latest.csv（3600 步上限、5 次重复、60 任务）

ga 在图侧是 600 步 / 30 个任务，其余三个是 2000 步 / 60 个任务 —— 步数差 3.3 倍、
任务数差 2 倍。任何把 0.7667 与 0.9667 并排的柱状图，差值里混着 episode 长度，
不是算法差异。

更隐蔽的是列集合：`无人机利用率 / 空载率 / 总飞行距离 / 顺路接入次数 / 禁飞区绕飞次数`
这 5 列只存在于 25 列 schema 的文件里，三个 2000 步基线（20 列 schema）根本没有这些列。
`pd.concat` 后它们在基线行上是 **NaN**，于是：
- matplotlib 拿到 NaN → 那三根柱子**直接不画**，图上看就是"只有 GA 有值"
- `console/static/index.html` 的表格 `cmpFmt()` → 渲染成「—」（正确）
- 同文件 :2712 的柱图 `r[m] ?? 0` → **补成 0**，于是"基线空载率 0 优于 GA 的 0.4994"
  这种假胜利就是这么来的

## 本模块的三条规则

1. **载体规则**：进入 `results/compare/` 的每个 CSV 都必须在 `manifest.json` 里登记口径
   （episode 步数上限、episode 数、随机种子集、指标 schema 版本、所属实验族）。
   没登记 = 拒绝。
2. **防伪规则**：manifest 里声明的 schema 指纹与步数必须与**磁盘上的实际表头/数据**一致。
   声明不能只靠人抄 —— 抄错或改文件不同步，门禁直接红。
3. **并列规则**：同一个对比表/同一张图的成员，必须 `(族, episode 上限, 生成任务数,
   schema 版本, episode 数, 种子集)` 完全相同。任一不同 → 拒绝，并打印冲突项。

`unknown` 是合法声明值，但它**不与另一个 unknown 之外的任何值相等**，也不允许出现在
被 `--check-group` 请求并列的成员里当作"已核实"：未登记口径的文件不得参与并列。

用法：
    python results/compare_gate.py --check-all          # 校验 manifest 与磁盘一致
    python results/compare_gate.py --check-group a.csv b.csv   # 校验某张表的成员可并列
    python results/compare_gate.py --render-readme       # 由 manifest 重渲染 README.md
    python results/compare_gate.py --selftest            # 自检：证明拒绝逻辑真的会拒

拒绝时退出码非 0，并把可读的拒绝原文打到 stdout。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
COMPARE_DIR = ROOT / "results" / "compare"
MANIFEST_PATH = COMPARE_DIR / "manifest.json"

# 口径声明里必须齐的字段。少任何一个 → 该文件不得进入任何并列。
REQUIRED_DECL_FIELDS = (
    "family",
    "episode_max_steps",
    "episode_count",
    "seed_set",
    "metrics_schema_version",
    "generated_tasks",
)
# 并列判据用的字段（族内必须逐项相等）
GROUP_KEYS = (
    "family",
    "episode_max_steps",
    "generated_tasks",
    "metrics_schema_version",
    "episode_count",
    "seed_set",
)
UNKNOWN = "unknown"


class GateRefused(Exception):
    """门禁拒绝。带上可读的拒绝原文，供 CLI 打印与测试断言。"""

    def __init__(self, message: str, conflicts: Any = None):
        super().__init__(message)
        self.message = message
        self.conflicts = conflicts or []


def header_of(csv_path: Path) -> List[str]:
    with io.open(csv_path, encoding="utf-8-sig", newline="") as f:
        for line in f:
            line = line.strip()
            if line:
                return [c.strip() for c in line.split(",")]
    raise ValueError("空文件：%s" % csv_path)


def schema_fingerprint(columns: Iterable[str]) -> str:
    """表头指纹：列数 + 列名集合的短哈希。

    用集合而不是顺序，因为同一 schema 的列顺序不该影响可比性；
    但列名缺一列就是不同 schema（20 列 vs 25 列正是本项目踩过的那个差）。
    """
    cols = sorted(columns)
    h = hashlib.sha1("|".join(cols).encode("utf-8")).hexdigest()[:12]
    return "n%d-%s" % (len(cols), h)


def data_rows(csv_path: Path) -> List[List[str]]:
    with io.open(csv_path, encoding="utf-8-sig", newline="") as f:
        lines = [l.rstrip("\r\n") for l in f if l.strip()]
    return [l.split(",") for l in lines[1:]]


def column_values(csv_path: Path, col: str) -> List[str]:
    hdr = header_of(csv_path)
    if col not in hdr:
        return []
    i = hdr.index(col)
    return [r[i] for r in data_rows(csv_path) if len(r) > i]


def load_manifest(path: Path = MANIFEST_PATH) -> Dict[str, Any]:
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def entry_for(man: Dict[str, Any], name: str) -> Dict[str, Any]:
    files = man.get("files") or {}
    if name not in files:
        raise GateRefused(
            "拒绝：%s 未在 results/compare/manifest.json 登记口径。\n"
            "      未登记 episode 步数上限 / episode 数 / 随机种子集 / 指标 schema 版本 / 所属实验族\n"
            "      的文件，不得被写进任何对比表或对比图。" % name)
    return files[name]


def verify_decl_against_disk(name: str, decl: Dict[str, Any]) -> List[str]:
    """防伪：声明必须与磁盘实际内容一致。返回不一致的条目列表。"""
    problems: List[str] = []
    p = COMPARE_DIR / name
    if not p.is_file():
        return ["声明了 %s，但磁盘上没有这个文件" % name]

    want = decl.get("metrics_schema_version")
    got = schema_fingerprint(header_of(p))
    if want != got:
        problems.append("metrics_schema_version 声明 %s，磁盘实际 %s（表头已变，声明未同步）"
                        % (want, got))

    missing = [f for f in REQUIRED_DECL_FIELDS if f not in decl]
    if missing:
        problems.append("口径字段缺失：%s" % ",".join(missing))

    steps_on_disk = sorted({v for v in column_values(p, "总步数")})
    declared = decl.get("declared_total_steps_on_disk")
    if declared is not None and steps_on_disk and [str(x) for x in declared] != steps_on_disk:
        problems.append("总步数列取值 声明 %s，磁盘实际 %s" % (declared, steps_on_disk))
    return problems


def check_all(man: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    declared = set((man.get("files") or {}).keys())
    on_disk = {p.name for p in COMPARE_DIR.glob("*.csv")}
    for name in sorted(on_disk - declared):
        problems.append("%s：磁盘上有、manifest 没登记（未登记口径，不得参与并列）" % name)
    for name in sorted(declared - on_disk):
        problems.append("%s：manifest 登记了、磁盘上没有" % name)
    for name in sorted(declared & on_disk):
        for msg in verify_decl_against_disk(name, man["files"][name]):
            problems.append("%s：%s" % (name, msg))
    return problems


def _group_value(decl: Dict[str, Any], key: str) -> Any:
    v = decl.get(key, UNKNOWN)
    if isinstance(v, list):
        return tuple(str(x) for x in v)
    return v


def disk_signature(name: str) -> Dict[str, Any]:
    """从磁盘**算**出可比性签名，不读任何人工声明的字符串。

    为什么要有这个：如果并列判据只比 manifest 里写的 episode_max_steps，那门禁真正依赖的
    是我手抄的那行字 —— 抄错、或改了 CSV 忘了改 manifest，判定就跟着错。
    这里直接用 CSV 的实际表头指纹与实际的 总步数/生成任务数 取值集合来判，
    声明与磁盘不一致会被 verify_decl_against_disk 单独抓住。

    没有该列时返回空集合（例如 hetero_vs_homo_* 根本没有总步数列）——
    空集合与非空集合不相等，所以不同实验族天然不会被判为可比。
    """
    p = COMPARE_DIR / name
    hdr = header_of(p)
    steps = sorted({v for v in column_values(p, "总步数")}, key=_num)
    tasks = sorted({v for v in column_values(p, "生成任务数")}, key=_num)
    return {
        "schema": schema_fingerprint(hdr),
        "total_steps_values": tuple(steps),
        "generated_tasks_values": tuple(tasks),
    }


def _num(s: str) -> float:
    try:
        return float(s)
    except (TypeError, ValueError):
        return float("nan")


def check_group(names: List[str], man: Dict[str, Any],
                strict: bool = False) -> Dict[str, Any]:
    """判断一组文件能否并列进同一张表/同一张图。不能则抛 GateRefused。

    两级判据，故意分开：
    - 普通级（默认）：**能证明不同**就拒。任一成员被 quarantine 也拒。
      episode 数/种子集声明为 unknown 的成员之间并列是允许的 —— 它们没有"已被证明不同"的
      口径列，B 组（三个 2000 步基线）就是这种情况。这不是放水：unknown 会原样出现在
      放行结果的 warnings 里，README 也写明了它不能声称可复现。
    - strict 级：额外拒绝任何带 unknown 口径的成员 —— 即"口径没有被真正记录"就不许并列。
      要的是"必须能证明同源"的场合用它。
    """
    if len(names) < 2:
        raise GateRefused("并列判据至少需要 2 个成员，收到 %d 个" % len(names))
    decls = {n: entry_for(man, n) for n in names}
    quarantined = sorted(n for n, d in decls.items() if d.get("quarantined"))

    conflicts = []

    # 主判据：**从磁盘算出来的**可比性签名。声明字符串写错也护不住，改 CSV 不改 manifest 也会被抓住。
    sigs = {n: disk_signature(n) for n in names}
    for field in ("schema", "total_steps_values", "generated_tasks_values"):
        vals = {n: sigs[n][field] for n in names}
        if len(set(map(repr, vals.values()))) > 1:
            conflicts.append({"kind": "disk_mismatch", "field": field,
                              "values": {n: (list(v) if isinstance(v, tuple) else v)
                                         for n, v in vals.items()}})

    # 次判据：manifest 里登记的、盘上算不出来的口径（episode 数、种子集、族）。
    for key in GROUP_KEYS:
        vals = {n: _group_value(d, key) for n, d in decls.items()}
        concrete = {n: v for n, v in vals.items() if v not in (UNKNOWN, None)}
        if len(set(map(repr, concrete.values()))) > 1:
            conflicts.append({"kind": "key_mismatch", "field": key,
                              "values": {n: (list(v) if isinstance(v, tuple) else v)
                                         for n, v in vals.items()}})
    if conflicts:
        pretty = []
        for c in conflicts:
            label = "盘上实测" if c["kind"] == "disk_mismatch" else "声明口径"
            pairs = ", ".join("%s=%s" % (n, c["values"][n]) for n in names)
            pretty.append("  [%s] 字段 %s 不一致 → %s" % (label, c["field"], pairs))
        if quarantined:
            pretty.append("  另：%s 已被隔离（manifest.quarantined），即使口径补齐也不得并列。"
                          % ", ".join(quarantined))
        raise GateRefused(
            "拒绝并列：%d 个成员口径不一致，混进同一张表/图后，读数差异里混着实验设置差异，"
            "不再是算法差异。\n%s" % (len(names), "\n".join(pretty)),
            conflicts=conflicts)

    # 口径算不出差别时，标签仍然要拦 —— 否则"同指纹但被判定不可对外"的文件会被放行。
    if quarantined:
        raise GateRefused(
            "拒绝并列：%s 已被隔离，不得与任何文件同图/同表。\n      隔离理由见 manifest：%s"
            % (", ".join(quarantined),
               " ".join(str(decls[n].get("note", ""))[:80] for n in quarantined)),
            conflicts=[{"kind": "quarantined", "file": n} for n in quarantined])
    for n in names:
        for other in decls[n].get("not_comparable_with", []):
            if other in names:
                raise GateRefused(
                    "拒绝并列：manifest 明确登记 %s 与 %s 不可并列。" % (n, other),
                    conflicts=[{"kind": "declared_incompatible", "a": n, "b": other}])

    warnings = []
    for n, d in decls.items():
        unk = [k for k in GROUP_KEYS if _group_value(d, k) == UNKNOWN]
        if unk:
            warnings.append("%s 的 %s 未登记（当次运行没写进 CSV）" % (n, ",".join(unk)))
    if strict and warnings:
        raise GateRefused(
            "拒绝并列（strict）：%d 个成员的口径未被真正记录，无法证明同源。\n      %s"
            % (len(warnings), "\n      ".join(warnings)),
            conflicts=[{"kind": "unproven_provenance", "detail": w} for w in warnings])

    return {"ok": True, "members": names, "strict": strict, "warnings": warnings,
            "group": {k: _group_value(decls[names[0]], k) for k in GROUP_KEYS}}


def group_key_of(decl: Dict[str, Any], name: str | None = None) -> Tuple:
    """给单个文件算"可比组键"，用于把入口读到的行分桶。

    能盘上实测的字段一律用实测值（schema / 总步数取值集合 / 生成任务数取值集合），
    只有盘上确实算不出来的（episode 数、种子集）才用声明值。这样"分组"不依赖手抄。
    """
    parts: List[Any] = [decl.get("family", UNKNOWN)]
    if name is not None:
        sig = disk_signature(name)
        parts.extend([sig["schema"], sig["total_steps_values"], sig["generated_tasks_values"]])
    for k in ("episode_count", "seed_set"):
        v = _group_value(decl, k)
        parts.append(v)
    return tuple(parts)


def check_entry_inputs(entry: str, names: List[str], man: Dict[str, Any],
                       allow_mixed: bool = False) -> Dict[str, List[str]]:
    """生成入口专用：把要一起读的文件按可比组分桶。

    默认拒绝任何跨组混读（allow_mixed=False）。允许时也只是分桶输出，调用方必须
    每个桶单独出图/出表，不得把两桶并到一张图里。
    """
    buckets: Dict[Tuple, List[str]] = {}
    for n in names:
        decl = entry_for(man, n)
        buckets.setdefault(group_key_of(decl, n), []).append(n)
    if len(buckets) > 1 and not allow_mixed:
        desc = []
        for key, members in buckets.items():
            desc.append("  桶 %s：%s" % (_fmt_key(key), ",".join(members)))
        raise GateRefused(
            "拒绝：%s 的输入跨了 %d 个口径组，不可并列成一张对比表/一张图。\n%s"
            % (entry, len(buckets), "\n".join(desc)),
            conflicts=[{"kind": "mixed_groups", "buckets":
                        {_fmt_key(k): v for k, v in buckets.items()}}])
    # 分桶通过之后，隔离声明仍要单独拦：它针对的是"这一族数据本身不可对外"，
    # 与成员之间是否同口径是两件事（只剩一个桶时上面那条不会触发）。
    if not allow_mixed:
        for n in names:
            if (man["files"][n]).get("quarantined"):
                raise GateRefused(
                    "拒绝：%s 读了已被隔离的 %s。隔离理由见 results/compare/manifest.json 的 note。"
                    % (entry, n),
                    conflicts=[{"kind": "quarantined", "file": n}])
    return {_fmt_key(k): v for k, v in buckets.items()}
    if len(buckets) > 1 and not allow_mixed:
        desc = []
        for key, members in buckets.items():
            desc.append("  桶 %s：%s" % (_fmt_key(key), ",".join(members)))
        raise GateRefused(
            "拒绝：%s 的输入跨了 %d 个口径组，不可并列成一张对比表/一张图。\n%s"
            % (entry, len(buckets), "\n".join(desc)),
            conflicts=[{"kind": "mixed_groups", "buckets":
                        {_fmt_key(k): v for k, v in buckets.items()}}])
    return {_fmt_key(k): v for k, v in buckets.items()}


# group_key_of 的字段顺序，_fmt_key 按此打标签
GROUP_KEY_FIELDS = ("family", "metrics_schema_version", "total_steps_values",
                    "generated_tasks_values", "episode_count", "seed_set")


def _fmt_key(key: Tuple) -> str:
    parts = []
    for k, v in zip(GROUP_KEY_FIELDS, key):
        if isinstance(v, tuple):
            v = "[" + ",".join(v) + "]"
        parts.append("%s=%s" % (k, v))
    return "(" + " ".join(parts) + ")"


def render_readme(man: Dict[str, Any]) -> str:
    """由 manifest 渲染 README.md —— 声明只有一个真源，文字表不能手抄。"""
    lines = [
        "# `results/compare/` 口径声明（自动生成，勿手改）",
        "",
        "> 本文件由 `python results/compare_gate.py --render-readme` 从同目录的",
        "> `manifest.json` 生成。**机器可读的那份是 `manifest.json`**；本文件只是它的展开，",
        "> 供在 Excel/WPS/论文表格这些**不走 `/api/compare`** 的读者看。",
        "> 一致性由 `console/test_compare_gate.py` 断言：手改本文件或改了 CSV 不改 manifest，测试就红。",
        "",
        man.get("headline", ""),
        "",
        "## 为什么这个目录危险",
        "",
    ]
    for b in man.get("why_it_matters", []):
        lines.append("- %s" % b)
    lines += ["", "## 逐文件口径", ""]
    lines.append("| 文件 | 实验族 | episode 步数上限 | episode 数 | 随机种子集 | 生成任务数 | schema 指纹 | 总步数列实际取值 |")
    lines.append("|---|---|---:|---:|---|---:|---|---|")
    for name in sorted((man.get("files") or {}).keys()):
        d = man["files"][name]
        seeds = d.get("seed_set")
        seeds = ",".join(map(str, seeds)) if isinstance(seeds, list) else str(seeds)
        lines.append("| `%s` | %s | %s | %s | %s | %s | `%s` | %s |" % (
            name, d.get("family"), d.get("episode_max_steps"), d.get("episode_count"),
            seeds, d.get("generated_tasks"), d.get("metrics_schema_version"),
            d.get("declared_total_steps_on_disk")))
    lines += ["", "## 逐文件并列许可", ""]
    lines.append("（这一节直接展开 manifest 里每个文件的 `comparable_with` / "
                 "`not_comparable_with`：在 Excel 里接线的人要的是「这个文件能不能跟我"
                 "手上那张表并排」这种逐文件答案，不是分组叙事。）")
    lines.append("")
    lines.append("| 文件 | 可与谁并列 | 不可与谁并列 |")
    lines.append("|---|---|---|")
    for name in sorted((man.get("files") or {}).keys()):
        d = man["files"][name]
        can = [c for c in (d.get("comparable_with") or []) if c != name]
        cannot = d.get("not_comparable_with") or []
        self_row = name in (d.get("comparable_with") or [])
        if can:
            can_txt = "、".join("`%s`" % c for c in can)
        elif self_row:
            can_txt = "（跨文件：**无**）本文件内部各行彼此可比"
        else:
            can_txt = "**无**（已被隔离）"
        if self_row and not can:
            can_txt += "；同文件内 %s 共用同一口径" % d.get("algorithm", "多算法")
        cannot_txt = ("、".join("`%s`" % c for c in cannot) if cannot else "（无）")
        lines.append("| `%s` | %s | 不可与 %s 并列 |" % (name, can_txt, cannot_txt))
    lines += ["", "## 能与谁并列、不能与谁并列", ""]
    for g in man.get("comparison_groups", []):
        lines.append("### %s" % g["title"])
        lines.append("")
        lines.append("- 可并列成员：%s" % ", ".join("`%s`" % m for m in g["members"]))
        for w in g.get("notes", []):
            lines.append("- %s" % w)
        lines.append("")
    lines += ["## 缺失列必须渲染为「空」，不是 0", ""]
    for w in man.get("missing_column_policy", []):
        lines.append("- %s" % w)
    lines += ["", "## 门禁", ""]
    lines.append("```bash")
    lines.append("python results/compare_gate.py --check-all")
    lines.append("python results/compare_gate.py --check-group frontend_greedy_metrics.csv backend_si_metrics.csv")
    lines.append("python results/compare_gate.py --selftest   # 证明拒绝逻辑真的会拒")
    lines.append("```")
    lines.append("")
    lines.append("拒绝时退出码非 0。入口（`results/plot_compare_metrics.py`、`console/server.py` 的")
    lines.append("`/api/compare`）默认调用本门禁，混口径直接拒。")
    lines.append("")
    return "\n".join(lines)


def selftest(man: Dict[str, Any]) -> int:
    """自检：门禁不是假绿灯 —— 必须既能拒也能放。"""
    print("[selftest] 用现有文件构造两组，验证拒绝/放行都真的生效")
    mixed = list(man["expected_refused_group"])
    try:
        check_group(mixed, man)
    except GateRefused as exc:
        print("[selftest] 混口径组 %s → 已拒绝（预期）" % mixed)
        print("---- 拒绝原文 ----")
        print(exc.message)
        print("----------------")
        refused = True
    else:
        print("[selftest] FAIL：混口径组竟然通过 —— 门禁是假绿灯")
        refused = False

    same = list(man["expected_comparable_group"])
    try:
        res = check_group(same, man)
        print("[selftest] 同口径组 %s → 通过（预期），warnings=%s"
              % (same, res["warnings"] or "(无)"))
        passed = True
    except GateRefused as exc:
        print("[selftest] FAIL：同口径组被误拒：%s" % exc.message)
        passed = False

    # strict 级必须把"口径没被真正记录"的那组挡下来，否则 strict 是个空开关
    try:
        check_group(same, man, strict=True)
    except GateRefused:
        print("[selftest] strict 级对同一组仍拒绝（预期，因为 ad-hoc 侧没登记种子集）")
        strict_ok = True
    else:
        print("[selftest] FAIL：strict 级竟然放行了未登记口径的组 —— strict 开关是空的")
        strict_ok = False
    return 0 if (refused and passed and strict_ok) else 1


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="results/compare 口径门禁")
    ap.add_argument("--check-all", action="store_true",
                    help="校验 manifest 与磁盘一致、所有文件都已登记")
    ap.add_argument("--check-group", nargs="+", metavar="CSV",
                    help="校验这几个文件能否并列进同一张表/图")
    ap.add_argument("--check-entry", metavar="NAME",
                    help="按入口名校验它实际读取的那组文件（plot / api_compare）")
    ap.add_argument("--render-readme", action="store_true", help="由 manifest 重写 README.md")
    ap.add_argument("--selftest", action="store_true", help="证明拒绝逻辑真的会拒、放行逻辑真的会放")
    ap.add_argument("--fingerprint", metavar="CSV", help="打印某文件表头指纹")
    args = ap.parse_args(argv)

    if args.fingerprint:
        print(schema_fingerprint(header_of(COMPARE_DIR / args.fingerprint)))
        return 0

    man = load_manifest()

    if args.selftest:
        return selftest(man)
    if args.render_readme:
        (COMPARE_DIR / "README.md").write_text(render_readme(man), encoding="utf-8")
        print("已重写 %s" % (COMPARE_DIR / "README.md"))
        return 0
    if args.check_all:
        problems = check_all(man)
        if problems:
            print("[FAIL] manifest 与磁盘不一致，共 %d 项：" % len(problems))
            for p in problems:
                print("  - %s" % p)
            return 1
        print("[OK] %d 个文件口径声明与磁盘一致" % len(man.get("files") or {}))
        return 0
    if args.check_entry:
        names = _entry_inputs(args.check_entry)
        try:
            buckets = check_entry_inputs(args.check_entry, names, man)
        except GateRefused as exc:
            print("[REFUSED] %s" % exc.message)
            return 1
        print("[OK] %s 的 %d 个输入落在 %d 个可比组：%s"
              % (args.check_entry, len(names), len(buckets),
                 json.dumps(buckets, ensure_ascii=False)))
        return 0
    if args.check_group:
        try:
            res = check_group(args.check_group, man)
        except GateRefused as exc:
            print("[REFUSED] %s" % exc.message)
            return 1
        print("[OK] 可并列：%s" % ", ".join(res["members"]))
        return 0
    ap.print_help()
    return 2


def _entry_inputs(entry: str) -> List[str]:
    if entry == "plot":
        sys.path.insert(0, str(ROOT / "results"))
        import plot_compare_metrics as pcm  # noqa: E402
        return list(pcm.CSV_FILES)
    if entry in ("api_compare", "server"):
        sys.path.insert(0, str(ROOT))
        import console.server as server  # noqa: E402
        return list(server._CSV_FILES)
    raise SystemExit("未知入口 %s（可用：plot / api_compare）" % entry)


if __name__ == "__main__":
    sys.exit(main())
