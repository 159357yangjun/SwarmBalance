# -*- coding: utf-8 -*-
"""常驻门：凡被引用的**冻结实验产物**，其 `core_source_sha256` 必须与盘上一致；
不一致则必须在 CHANGELOG 里有该产物的**具名过期声明**，否则红。

## 为什么要有这条（一手来历）
E1↔E0 等价门那条红查了两轮才定性，全靠 `results/experiments/*/reproducibility.json` 里
**早就存在**的 `core_source_sha256` 字段 —— 但它从来没人和盘上比过。
⇒ "字段在、没人比"是侥幸，不是保障。本门把它变成常驻对账（主控裁定 (二) 批准入门）。

## 三态判据（缺一即是一条会逼人被关掉的门）
| 情形 | 处置 | 为什么 |
|---|---|---|
| 指纹全符 | **绿**（计入退出码） | 正常态 |
| 有漂移 + CHANGELOG 有该产物的具名过期声明 | **降级为信息**，印出是哪条声明，不进退出码 | 基线随仓库推进而过期是常态；要求"每次改动都重跑实验"不现实，那只会让人把门删掉 |
| 有漂移 + **无**声明 | **红** | 这才是真正要拦的：有人拿一份悄悄失效的参照物下了结论 |
| 产物/`reproducibility.json` 不存在 | **红**（`[FP_BLIND]`） | 读不到 ≠ 通过 |

⚠ 关键设计点：**校验范围 = 被代码或文档引用到的产物**，不是"盘上所有产物"。
理由：孤儿产物没人引用 ⇒ 它过期不误导任何人；而"引用了却没核对"才是事故来源。
范围从盘上+仓内文本**现算**（不抄手写名单），并印 `referenced / with_pin / drifted / declared` 四个数对账
—— 沿用 P3 覆盖率恒等式的形状。

短码：[FP_DRIFT_UNDECLARED] / [FP_BLIND] / [FP_NO_REFERENCE_FOUND] / [FP_TEAR_DOWN]
退出码：任一未声明漂移或量具瞎 = 1。参与 discover（常驻门）。
"""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import re
import shutil
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ART_DIR = ROOT / "results" / "experiments"
CHANGELOG = ROOT / "CHANGELOG.md"

#: 产物目录名的形状（名字_日期-时间）。用它去**扫引用文本**，而不是写死一份名单。
DIR_RE = re.compile(r"\b([a-z0-9][a-z0-9_]*_\d{8}-\d{6})\b")

#: 扫描范围：只有这些地方的文本里的目录名算"被引用"。
REF_GLOBS = ("console/**/*.py", "frontend/**/*.py", "experiments/**/*.py", "*.py",
             "docs/**/*.md", "README.md", "CHANGELOG.md")

#: 具名过期声明的标记词。**必须显式带产物目录名**才算声明覆盖到那个产物（见 _declarations）。
EXPIRY_MARKS = ("pending revalidation", "已声明过期", "夹具失效", "已过期")

#: 覆盖面判据（test_D）只对**这个日期当天或之后生成**的产物生效。
#: 依据是 `git log -S` 实测：SHARED_SOURCES 这份清单本身诞生于 **c7d14ea（2026-09-28）**，
#: 早于它的产物（如 conclusion_20260911-043701，pin 只有 8 个键、无 config/）当时没有"清单该含哪些目录"
#: 这个概念 ⇒ 拿今天的清单去要求它，报出来的是一条不存在的缺失（本轮第一版就误红过一次）。
#: ⚠ 这不是白名单，是**可判定性的下限**：新产物一律受此约束；要改这个日期必须给出对应的清单变更提交号。
COVERAGE_SINCE_DATE = "2026-09-28"


def referenced_artifacts():
    """-> {artifact_dir_name: {出现位置}}：从盘上现算"被引用的冻结产物"集合。

    ⚠ 不写死名单：写死了就会漏（本次事故的形状正是"没人知道 e0_baseline 已被引用着"）。
    """
    refs = {}
    for pat in REF_GLOBS:
        for f in sorted(ROOT.glob(pat)):
            if not f.is_file() or "__pycache__" in f.parts:
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = f.relative_to(ROOT).as_posix()
            for name in set(DIR_RE.findall(text)):
                if (ART_DIR / name).is_dir():
                    refs.setdefault(name, set()).add(rel)
    return refs


def _declarations_from(lines):
    """声明判定的唯一实现：吃**行列表**，返回 {artifact: (1-based 行号, 该行原文)}。

    判据 = 同一行里既有该产物目录名、又有 EXPIRY_MARKS 之一。
    ⚠ 刻意要求**同行**：只"文件里出现过 pending revalidation"不算覆盖到某个产物，
      那等于给任意漂移发万能通行证（逃生口）。这条不是注释里的说法——test_C 用两行 vs 同行的
      合成文本实测过它的牙。
    ⚠ 单独抽出来成"吃行列表"的纯函数，是为了让夹具能在**内存里**喂样本；
      若只有读文件的版本，测这条判据就得改盘上 CHANGELOG（那是已入库证据）。
    """
    out = {}
    for i, line in enumerate(lines, start=1):
        if not any(m in line for m in EXPIRY_MARKS):
            continue
        for name in set(DIR_RE.findall(line)):
            out.setdefault(name, (i, line.strip()[:120]))
    return out


def _declarations():
    """-> {artifact: (行号, 该行原文)}：CHANGELOG 里对该产物的具名过期声明。"""
    if not CHANGELOG.is_file():
        return {}
    return _declarations_from(CHANGELOG.read_text(encoding="utf-8").splitlines())


def pin_state(name, art_root=None):
    """-> (status, detail)。status ∈ ok / drifted / blind(读不到)。

    `art_root` 只为**夹具**开：两面夹具要在临时目录里造一份假产物，
    但绝不能往真 `results/experiments/` 下落东西（那是已入库证据）。
    默认走真实 ART_DIR ⇒ 生产判据路径上没有任何可注入的口子。
    """
    root = pathlib.Path(art_root) if art_root else ART_DIR
    p = root / name / "reproducibility.json"
    if not p.is_file():
        return "blind", "缺 reproducibility.json"
    try:
        with io.open(p, encoding="utf-8") as fh:
            d = json.load(fh)
    except (ValueError, OSError) as exc:
        return "blind", "reproducibility.json 解析失败 %s" % type(exc).__name__
    pin = d.get("core_source_sha256") or {}
    if not pin:
        return "blind", "无 core_source_sha256 字段"
    #: 钉住的路径怎么解析：真实产物用 ROOT（字段里就是仓内相对路径）；
    #:   夹具用 art_root **本身**（不是它的 parent —— 第一版写成 parent，于是假产物永远 MISSING，
    #:   而 MISSING 又判 drifted ⇒ 正面证人"指纹相符应判 ok"当场不过，把这条暴露了出来）。
    base = ROOT if not art_root else root
    bad = []
    for rel, want in sorted(pin.items()):
        q = base / rel
        got_now = hashlib.sha256(q.read_bytes()).hexdigest() if q.is_file() else None
        if got_now is None:
            bad.append("%s MISSING" % rel)
        elif got_now != want:
            bad.append("%s pin=%s now=%s" % (rel, want[:12], got_now[:12]))
    return ("drifted", ";".join(bad)) if bad else ("ok", "%d/%d match" % (len(pin), len(pin)))


class FrozenArtifactSourcePin(unittest.TestCase):
    def test_A_referenced_artifacts_are_pinned_or_declared(self):
        refs = referenced_artifacts()
        self.assertTrue(refs, "[FP_NO_REFERENCE_FOUND] 仓内一个冻结产物都没引用到 ⇒ "
                              "扫描面或目录形状变了，本门成了空转")
        decls = _declarations()
        rows, undeclared = [], []
        for name in sorted(refs):
            st, detail = pin_state(name)
            declared = name in decls
            rows.append((name, st, declared, detail))
            if st == "blind":
                self.fail("[FP_BLIND] %s：%s ⇒ 读不到指纹不算通过（且它正被 %s 引用）" % (
                    name, detail, ", ".join(sorted(refs[name])[:2])))
            if st == "drifted" and not declared:
                undeclared.append("%s ← %s\n      引用于: %s" % (
                    name, detail, ", ".join(sorted(refs[name])[:3])))
        n_ok = sum(1 for _n, s, _d, _x in rows if s == "ok")
        n_drift = sum(1 for _n, s, _d, _x in rows if s == "drifted")
        n_decl = sum(1 for _n, s, d, _x in rows if s == "drifted" and d)
        print("[FP_VERDICT] referenced=%d with_pin=%d drifted=%d declared=%d ok=%d "
              "undeclared=%d exit_criterion=(undeclared==0) —— 已声明的漂移降级为信息不进退码" % (
                  len(rows), len(rows), n_drift, n_decl, n_ok, len(undeclared)))
        for name, st, declared, detail in rows:
            mark = "OK" if st == "ok" else ("DECLARED" if declared else "UNDECLARED")
            print("[FP_ARTIFACT] %-38s state=%-12s pinned_files=%s" % (name, mark, detail[:70]))
            if st == "drifted" and declared:
                ln, txt = decls[name]
                print("[FP_DECLARATION] %s CHANGELOG:%d | %s" % (name, ln, txt))
        self.assertEqual(undeclared, [],
                         "[FP_DRIFT_UNDECLARED] 这些被引用的冻结产物源码指纹已漂移但 CHANGELOG 里"
                         "没有带其目录名的过期声明 ⇒ 有人可能正拿一份失效参照下结论：\n  "
                         + "\n  ".join(undeclared)
                         + "\n  处置：要么重生成该产物，要么在 CHANGELOG 加一行**带目录名**的"
                           "`pending revalidation` 声明（不许改本门判据）。")

    def test_D_pin_list_covers_every_pinned_directory(self):
        """覆盖面（不是漂移面）：产物钉住的清单必须**覆盖到 SHARED_SOURCES 现在钉的每个顶层目录**。

        为什么单开一条：`pin_state` 只比"字段里列了的那些文件"，所以一旦生成器侧漏掉某个承重文件
        （Phase 1A 把 A* 抽成 `frontend/route_planner.py` 就是这种漏），所有旧产物的 pin 仍然"全数相符"，
        本门会一路绿，而它守的那个"行为没变"根本没人证过。⇒ 期望值来自定义，不来自当前读数。

        ⚠ 判据是**目录级**、不是逐文件：逐文件会让每次重构都得重录全部历史产物，那逼人放宽判据；
          目录级只在"整类源码脱离钉住范围"时报警，正是本轮那种缺口。
        """
        import importlib.util as _il
        _spec = _il.spec_from_file_location("rc_for_coverage", ROOT / "console" / "_readme_counts.py")
        rc = _il.module_from_spec(_spec)
        _spec.loader.exec_module(rc)      # 同 test_readme_counts 的加载方式：本文件在 discover 下 sys.path[0] 不含 console/
        want_shared = set(rc.pinned_shared_files())

        refs = referenced_artifacts()
        missing_all, not_comparable, covered = [], [], 0
        for name in sorted(refs):
            p = ART_DIR / name / "reproducibility.json"
            if not p.is_file():
                continue
            with io.open(p, encoding="utf-8") as fh:
                doc = json.load(fh)
            pin = doc.get("core_source_sha256") or {}
            miss = sorted(want_shared - set(pin))
            if not miss:
                covered += 1
                continue
            # ⚠ 只要求 **SHARED_SOURCES**（与算法无关的共用执行路径），不要求 ALGORITHM_SOURCES：
            #   后者按产物实际跑过的算法登记（`write_manifest` 里 `for a in algos`），
            #   greedy-only 的 E0 基线本来就不该有 backend_si/*。把它们算进分母会报出 7 处假阳性 ——
            #   本轮第一版就这么干了，等于指着一条不存在的缺失喊红。
            # ⚠ 判据是**逐文件**，不是目录级：目录级会把 route_planner 这种缺口掩盖成
            #   "frontend 里有几个键就够了"，而它正是本条要抓的东西。
            # ⚠ 必须按**产物自己的生成日期**分档：这份清单本身是 c7d14ea（2026-09-28）才建立的，
            #   早于它的产物（conclusion_20260911-043701，pin 只有 8 键）没有"该含哪些文件"的概念。
            #   这不是白名单，是**可判定性的下限**；改这个日期必须给出对应的清单变更提交号。
            gen = str(doc.get("generated_at_utc") or "")[:10]
            if gen and gen < COVERAGE_SINCE_DATE:
                not_comparable.append("%s(gen=%s 早于 %s ⇒ 当时还没有这份清单，缺 %d 个文件不计)" % (
                    name, gen, COVERAGE_SINCE_DATE, len(miss)))
                continue
            missing_all.append("%s 缺 %d 个承重文件: %s" % (name, len(miss), ", ".join(miss[:4])))

        # 恒等式：受检 = 全覆盖 + 欠覆盖 + 早于清单（不可比）。三个桶必须闭合，
        # 否则某个桶既不算通过也不算失败。
        # 欠覆盖再分两档：**具名声明过的**降级为信息（与 test_A 的漂移通道同一套口径），
        # 没声明的才拦退码 —— 否则"扩一次清单"会把所有历史产物变成永久红，那逼人放宽判据。
        undeclared_cov = [m for m in missing_all if m.split(" ")[0] not in _declarations()]
        n_under_decl = len(missing_all) - len(undeclared_cov)
        print("[FP_COVERAGE] pinned_shared_files=%d since=%s artifacts_checked=%d fully_covered=%d "
              "under_covered=%d under_declared=%d under_undeclared=%d pre_baseline_exempt=%d "
              "identity=(checked==covered+under+exempt) exit_criterion=(under_undeclared==0)" % (
                  len(want_shared), COVERAGE_SINCE_DATE, len(refs), covered,
                  len(missing_all), n_under_decl, len(undeclared_cov), len(not_comparable)))
        self.assertEqual(covered + len(missing_all) + len(not_comparable), len(refs),
                         "[FP_BUCKET_GAP] 三个桶不闭合：%d+%d+%d != %d ⇒ 有产物既没算证过也没算漏检" % (
                             covered, len(missing_all), len(not_comparable), len(refs)))
        for m in missing_all[:8]:
            mark = "已具名声明" if m.split(" ")[0] in _declarations() else "**无声明**"
            print("[FP_UNDER_COVERED] %s [%s]" % (m, mark))
        for m in not_comparable[:8]:
            print("[FP_NOT_COMPARABLE] %s ⇒ 不算漏检、也不算证过" % m)
        self.assertEqual(undeclared_cov, [],
                         "[FP_UNDER_COVERED_UNDECLARED] 这些被引用的冻结产物没钉住生成器现在钉的某些源码文件，"
                         "且 CHANGELOG 里没有带其目录名的具名说明 ⇒ \"pin 相符\"对它们不构成行为不变的证据（%d 处）：\n  "
                         % len(undeclared_cov) + "\n  ".join(undeclared_cov))

    def test_B_gate_has_teeth_both_faces(self):
        """两面夹具（全在临时目录里，**不往 results/experiments/ 下落任何东西**）：
        漂移无声明必须红、指纹相符必须绿、读不到必须判 blind。

        ⚠ 期望值来自**判据定义本身**（三态表），不是"看当前跑出来什么"。
        """
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="fp_teeth_"))
        art = tmp / "fake_artifact_20260101-000000"
        meta = art / "reproducibility.json"
        src = tmp / "payload.py"
        try:
            art.mkdir(parents=True)
            src.write_text("X = 1\n", encoding="utf-8")
            good = hashlib.sha256(src.read_bytes()).hexdigest()
            meta.write_text(json.dumps({"git_commit": "deadbeef",
                                         "core_source_sha256": {"payload.py": good}}), encoding="utf-8")
            # 面①：指纹相符 ⇒ ok（正面证人：没有它，一条永远红的门和一条有牙的门长得一样）
            st, detail = pin_state("fake_artifact_20260101-000000", art_root=tmp)
            self.assertEqual(st, "ok", "[FP_BLIND] 指纹相符时判成 %s(%s) ⇒ 正面证人不过" % (st, detail))
            # 面②：改了被钉的文件 ⇒ drifted
            src.write_text("X = 2\n", encoding="utf-8")
            st2, detail2 = pin_state("fake_artifact_20260101-000000", art_root=tmp)
            self.assertEqual(st2, "drifted",
                             "[FP_NO_TEETH] 改了被钉文件仍判 %s ⇒ 本门咬不住漂移" % st2)
            # 面③：钉的文件消失 ⇒ 仍是 drifted（MISSING 也算不一致），不得静默 ok
            src.unlink()
            st3, d3 = pin_state("fake_artifact_20260101-000000", art_root=tmp)
            self.assertEqual(st3, "drifted", "[FP_NO_TEETH] 被钉文件消失仍判 %s ⇒ 漏检" % st3)
            self.assertIn("MISSING", d3, "[FP_BLIND] MISSING 没进读数 ⇒ 分不清改内容与删文件")
            # 面④：读不到指纹 ⇒ blind（绝不等于通过）
            meta.write_text("{}", encoding="utf-8")
            st4, _ = pin_state("fake_artifact_20260101-000000", art_root=tmp)
            self.assertEqual(st4, "blind", "[FP_BLIND] 无指纹字段却判 %s ⇒ 读不到被当成了通过" % st4)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self.assertFalse(tmp.exists(), "[FP_TEAR_DOWN] 临时夹具目录还在：%s" % tmp)
            stray = [f.name for f in (ROOT / "results" / "experiments").glob("fake_artifact*")]
            self.assertEqual(stray, [], "[FP_TEAR_DOWN] 夹具污染了真产物目录：%s" % stray)

    def test_C_declaration_requires_the_named_artifact(self):
        """判别式：声明必须**带目录名**才算覆盖，否则是万能通行证。

        ⚠ 本用例原先只在真 CHANGELOG 上测"存在的那几条都带名"，那是**只有阳性面**的判据：
          它证明不了"名字与标记词分在两行时不算声明"（第三十九笔入档时我自己把这条列为残余边界 (iii)）。
          本轮把它从"登记为盲区"改成"实测过"——加一条合成两行文本喂进 _declarations_from。
        ⚠ `decls` 是**引用型产物集合上的**声明，不是全表：同一行里同时提到多个产物目录名时，
          那一行会给每个被点名的产物都发一份声明。所以断言只能要求"该行含某个被引用的产物名"，
          不能要求"该行含我正在循环的那个名字" —— 第四十二笔补覆盖面声明时就这样误红过一次
          （一行里同时写了 235335 与 221039，被判"没写出 221039"）。
        """
        decls = _declarations()
        refs = set(referenced_artifacts())
        for name, (ln, txt) in list(decls.items()):
            hit = [r for r in refs if r in txt]
            self.assertTrue(hit,
                            "[FP_BLIND] CHANGELOG:%d 的声明没写出任何被引用的目录名 ⇒ 不该算覆盖" % ln)
        # 反向证人：光有标记词、不带任何目录名的行，不应产出任何声明
        bare = [l for l in CHANGELOG.read_text(encoding="utf-8").splitlines()
                if any(m in l for m in EXPIRY_MARKS) and not DIR_RE.search(l)]
        self.assertTrue(bare or decls,
                        "[FP_BLIND] 既无带名声明也无裸标记 ⇒ 无法证明这条判据真的在筛")

        #: 两面夹具（全在内存字符串里，不碰盘上 CHANGELOG）：同一份内容，
        #:   只改"目录名与标记词是否同行"这一件事 ⇒ 行数差就是"同行"这条判据的牙。
        two_line = ("| `x_split_20260101-000000` | 8 | 3 | ...\n"
                    "状态列写在下一行：pending revalidation\n")
        same_line = ("| `x_split_20260101-000000` | 8 | 3 | ... pending revalidation |\n")
        d_split = _declarations_from(two_line.splitlines())
        d_same = _declarations_from(same_line.splitlines())
        self.assertNotIn("x_split_20260101-000000", d_split,
                         "[FP_BLANKET_PASS] 目录名与标记词分在两行仍算声明 ⇒ '同行'只是注释里的说法，"
                         "实际等于给任意漂移发通行证")
        self.assertIn("x_split_20260101-000000", d_same,
                      "[FP_NO_TEETH] 名字与标记词同行却没被认成声明 ⇒ 声明通道自己失效了")
        print("[FP_DECL_TWO_LINE] split_declared=%d same_line_declared=%d "
              "exit_criterion=(split==0 and same_line==1)"
              % (len(d_split), len(d_same)))
        print("[FP_DECL_SHAPE] named_declarations=%d bare_marker_lines=%d "
              "exit_criterion=(each declaration carries its artifact dir name)" % (len(decls), len(bare)))


if __name__ == "__main__":
    unittest.main()
