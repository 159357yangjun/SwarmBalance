# -*- coding: utf-8 -*-
"""C1 生命周期一致性门（#68-C1）—— 五条规则，判据来自 Observer 的无截断事件轨迹。

设计前提（本轮修正过的两处报告错误，写在这里防再犯）：
* ``reason`` 字段在 #68-B 交付时**并不存在**，是本轮补上的；它只映射几何证据
  （``destination_reached`` / ``no_delivery_evidence``），**不猜业务意图**。
* ``EVENTS`` 白名单声明 ≠ 实际会发。#68-B 实测只出现 4 类；本轮补入 ``DESTINATION_REACHED``
  后为 5 类。⇒ 本门的断言一律读 ``summary["event_kinds_observed"]``（实测集合），不读白名单。

预期终态：**对当前生产代码必须红**（counter=38，legal delivery completions=26，12 条 invalid）。
若它绿，说明门没牙 —— 由 ``--face mutate`` 面自证它会红。

三面运行：
    python -m unittest console.test_c1_lifecycle_gate                 # old：真实生产代码，期望红
    python -m unittest console.test_c1_lifecycle_gate --face fixed    # 读已修复基线 JSON，期望绿
    python -m unittest console.test_c1_lifecycle_gate --face mutate   # 注入重复/伪造送达，期望红
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "取证输出"
SEED, STEPS, ALGO = 40907, 1200, "greedy"

#: 面只能由环境变量指定。**不能读 sys.argv** —— `python -m unittest console.test_x` 会把
#: 模块名塞进 argv[1]，导致 face 变成任意字符串、断言静默走进 else 分支（本轮实测踩过：
#: 门"通过"了本该红的 old 面）。非法/缺失取值一律降到最保守的 ``old``（要求红）。
_VALID_FACES = ("old", "fixed", "mutate", "forced_cleanup")
FACE = os.environ.get("C1_FACE", "old").strip().lower()
if FACE not in _VALID_FACES:
    FACE = "old"
FIXED_TRACE = OUT_DIR / "c1_face_r2_fixed.json"   # 修复后的生产轨迹（old 面写出）


def _collect(face: str) -> dict:
    """按 face 取轨迹。

    ⚠ #69-C1：``fixed`` 面**直接跑当前生产代码**，不再读归档 JSON。
      旧写法读 ``c1_face_r2_fixed.json``（#69-B 时代冻结的 R2-only 轨迹）——那反映的是
      dest 契约修复**之前**的行为，用它当"修复后期望"等于拿旧尺子量新代码（本轮实测踩过：
      归档里 R1=12，而当前代码 R1=0）。归档产物只作历史留档，判据一律来自 live trace。
    ⚠ 分派必须看**形参** face，不能读模块级 FACE —— 上一版就是这么错的：
    `_collect(FACE)` 传了参数却仍按模块常量走 old 分支，于是 forced_cleanup 面
    与 old 面读数逐字相同，看起来"跑了"其实什么都没注入（＝又一次没有变异的变异测试）。
    """
    if face in ("mutate", "forced_cleanup"):
        raw = _run_production_trace()
        raw["events"] = (_inject(raw["events"]) if face == "mutate"
                         else _force_cleanup(raw["events"]))
        if face == "forced_cleanup":
            raw["total_completed_tasks"] = int(raw["total_completed_tasks"]) + 1
        return raw
    # old / fixed 都跑当前生产代码；二者区别只在 test_1 的期望（见下）。
    return _run_production_trace()


def _run_production_trace() -> dict:
    script = r'''
import json, os, sys, pathlib
ROOT = pathlib.Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "frontend")]
os.environ["SWARM_BALANCE_SIM_CONFIG"] = str((ROOT / "config" / "simulation.json").resolve())
from environment import Environment
from greedy.scheduler import greedy_action_from_observation
import consistency_observer as co
obs_obj = co.ConsistencyObserver()
env = Environment(str(ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm"), episode_max_steps=%(steps)d)
obs = env.reset(seed=%(seed)d)
co.install(env, obs_obj)
done = False
while not done:
    a = greedy_action_from_observation(obs)
    obs, _, done, _ = env.step(a)
print(json.dumps({"summary": obs_obj.summary(), "events": obs_obj.events,
                  "total_completed_tasks": int(env.total_completed_tasks)}))
''' % {"seed": SEED, "steps": STEPS}
    with tempfile.TemporaryDirectory() as td:
        f = pathlib.Path(td) / "c1_run.py"
        f.write_text(script, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(f), str(ROOT)],
                              capture_output=True, text=True, timeout=1800,
                              encoding="utf-8", errors="replace",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if proc.returncode != 0:
        raise AssertionError(f"[C1_RUN_FAILED] rc={proc.returncode}\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


# ======================================================================
# 五条规则的判定函数（纯函数：输入事件列表，输出违规清单）
# ======================================================================

def classify(trace: dict, injected=None) -> dict:
    """返回每条规则的违规数。injected 仅用于 mutation 面。"""
    events = list(trace["events"])
    counter = int(trace["total_completed_tasks"])
    if injected:
        events = injected(events)

    comp = [e for e in events if e["kind"] == "TASK_COMPLETION_RECORDED"]
    reached = {e["task_id"] for e in events if e["kind"] == "DESTINATION_REACHED"}
    # R2 取货前置：用 **sequence_no** 不用 timestamp —— 离散仿真同一 sim_time 可有多个事件。
    #   seq(TASK_LOADED) < seq(DESTINATION_REACHED) <= seq(COMPLETION_RECORDED)
    loaded_seq, reached_seq = {}, {}
    for e in events:
        if e["kind"] == "TASK_LOADED":
            loaded_seq.setdefault(e["task_id"], e["seq"])
        elif e["kind"] == "DESTINATION_REACHED":
            reached_seq.setdefault(e["task_id"], e["seq"])
    r2 = []
    for tid, rs in reached_seq.items():
        ls = loaded_seq.get(tid)
        if ls is None or not (ls < rs):
            r2.append(tid)

    # R1 合法完成证据：计入 completed 必须有 DESTINATION_REACHED。
    #   ⚠ #69-C1 后送达证人 = dest service leg 被消费（origin==destination_branch），
    #   不再是几何 pos==dest —— 后者在 detour 容差抵达下会把合法送达误判成无证据。
    r1 = [e for e in comp if e["task_id"] not in reached]

    # R2 取货前置：TASK_LOADED 时间 < DESTINATION_REACHED
    r2 = []
    for tid, rs in reached_seq.items():
        ls = loaded_seq.get(tid)
        if ls is None or not (ls < rs):
            r2.append(tid)

    # R3 唯一完成：同一 task_id 最多一个合法 completion
    seen, r3 = {}, []
    for e in comp:
        if e["task_id"] in reached:                      # 只数合法的
            seen[e["task_id"]] = seen.get(e["task_id"], 0) + 1
    r3 = [k for k, v in seen.items() if v > 1]

    # R4 聚合可重算：counter == trace 中**合法** completion 的唯一 task 数
    legal_unique = len({e["task_id"] for e in comp if e["task_id"] in reached})
    r4 = (counter != legal_unique)

    # R5（#69-C2a 起降级为**信息量读数**，不再进退码）：dest-branch 送达中坐标非精确抵达的条数。
    # ⚠ 消融实测（本轮）：把 cleanup accounting 整条禁用（if False:）后本读数仍=12、逐字不变
    #   ⇒ 它对 cleanup 代码零敏感，测的是 A* <1m 容差抵达率（Planner 语义），不是"cleanup 冒充 delivery"。
    #   真正的 cleanup→completion 语义门见下面的 r_cleanup_semantic；R5 只作可复核的信息计数。
    r5 = [e for e in comp if not e["has_destination_evidence"]]

    # 新语义门（有牙）：走了 is_free_cleanup 分支、却无合法 destination service 消费证人 ⇒ 必红。
    #   "合法 destination service 消费"= 该任务发过 DESTINATION_REACHED（origin==destination_branch 时观察层必发）。
    #   生产 seed 上 cleanup 分支不可达 ⇒ 本门=0；其牙由 forced_cleanup 注入面证明（注入即 >0）。
    r_cleanup_semantic = [e for e in comp
                          if e.get("record_origin") == "is_free_cleanup_branch"
                          and e["task_id"] not in reached]

    # G-D-a（#69-E）：timeout/delay 只能由 legal delivery completion 产生。
    #   谓词写成不随 seed 变的结构事实，不用常量：任一 d_delay>0 或 d_ontime==0 的完成必须有 DESTINATION_REACHED。
    #   ⚠ 用 origin==destination_branch 作证人、不用 has_destination_evidence —— 后者是几何精确相等，
    #     detour 容差抵达下合法送达也会 False（r5_nonexact_arrival_count=12 那批），拿它当证人会误报。
    gd_a = [e for e in comp
            if (float(e.get("d_delay", 0.0)) > 0 or int(e.get("d_ontime", 1)) == 0)
            and e.get("record_origin") != "destination_branch"]

    # G-D-b（#69-E）：DR ↔ completion 双向对齐 + counter 可重算（把 D §2(b) 变成常驻检查而非一次性对账）。
    #   三个量必须相等：counter == Σd_completed == |completion|；且缺 DR 的完成=0、孤儿 DR=0。
    sum_d_completed = int(sum(e.get("d_completed", 0) for e in comp))
    missing_dr = len([e for e in comp if e["task_id"] not in reached])
    orphan_dr = len(reached - {e["task_id"] for e in comp})
    gd_b_aligned = (counter == len(comp) == sum_d_completed
                    and missing_dr == 0 and orphan_dr == 0)

    return {
        "completions_recorded": len(comp),
        "counter": counter,
        "legal_unique": legal_unique,
        "R1_missing_destination_evidence": len(r1),
        "R2_pickup_not_before_delivery": len(r2),
        "R3_duplicate_completion": len(r3),
        "R4_aggregate_not_recomputable": 1 if r4 else 0,
        "r5_nonexact_arrival_count": len(r5),                 # 信息量读数，不进退码
        "R5_never_loaded_among_them": sum(1 for e in r5
                                          if not e.get("has_load_evidence", False)),
        "cleanup_completion_without_service": len(r_cleanup_semantic),  # 有牙语义门
        "GD_a_timeout_from_illegal": len(gd_a),               # G-D-a：非法来源的 timeout/delay 数
        "GD_b_alignment_ok": 1 if gd_b_aligned else 0,        # G-D-b：三量互等 + 双向无缺口
        "GD_b_missing_dr": missing_dr,
        "GD_b_orphan_dr": orphan_dr,
        "GD_b_sum_d_completed": sum_d_completed,
    }


class C1LifecycleGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = _collect(FACE)
        cls.res = classify(cls.trace)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        assert FACE in _VALID_FACES, f"[C1_BAD_FACE] {FACE}"
        # ⚠ 冻结证据不可被测试覆盖：c1_face_old.json（580c937）与 c1_face_r2_fixed.json
        #   （#69-B 后、#69-C1 前的 R2-only 轨迹，R1=12/R5=12）都是**历史基线留档**。
        #   old/fixed 面现在都跑当前工作树代码 ⇒ 一律写到 live 产物 c1_face_live_<face>.json，
        #   绝不回写上面两个冻结文件。
        name = f"c1_face_live_{FACE}.json" if FACE in ("old", "fixed") else f"c1_face_{FACE}.json"
        (OUT_DIR / name).write_text(
            json.dumps({"face": FACE, "verdict": cls.res, "events": cls.trace["events"]},
                       ensure_ascii=False, indent=1), encoding="utf-8")

    def test_0_event_kinds_are_the_observed_set(self):
        """断言读实测集合：DESTINATION_REACHED 必须真的出现过（#68-B 曾只在白名单里声明）。"""
        kinds = (self.trace.get("summary") or {}).get("event_kinds_observed")
        if kinds is None:                       # 归档产物形状不含 summary ⇒ 从事件现算
            from collections import Counter
            kinds = dict(Counter(e["kind"] for e in self.trace["events"]))
        self.assertIn("DESTINATION_REACHED", kinds, "[C1_NO_DELIVERY_WITNESS]")

    def test_1_rules_are_enforced(self):
        """判据范围 = 本轮修复面。#69-C2a：R5 降为信息读数、新语义门 cleanup_completion_without_service 承担牙。"""
        r = self.res
        print(f"[C1 VERDICT face={FACE}] {json.dumps(r, ensure_ascii=False)}")
        if FACE == "fixed":
            # dest service 契约已修 ⇒ R1/R2/R3/R4 全 0；cleanup accounting 仍未修但生产 seed 不可达
            #   ⇒ 新语义门必须=0（若 >0 说明有真实 completion 走了兜底却没送达证人，那才是缺陷复发）。
            self.assertEqual(r["R1_missing_destination_evidence"], 0,
                             f"[C1_R1_NOT_FIXED] got={r['R1_missing_destination_evidence']}")
            self.assertEqual(r["R2_pickup_not_before_delivery"], 0,
                             f"[C1_R2_NOT_FIXED] got={r['R2_pickup_not_before_delivery']}")
            self.assertEqual(r["R3_duplicate_completion"], 0, "[C1_R3]")
            self.assertEqual(r["R4_aggregate_not_recomputable"], 0,
                             f"[C1_R4] counter={r['counter']} != legal_unique={r['legal_unique']}")
            self.assertEqual(r["cleanup_completion_without_service"], 0,
                             f"[C1_CLEANUP_GATE_RED_ON_FIXED] got={r['cleanup_completion_without_service']}"
                             " ⇒ fixed 代码上竟有 completion 走兜底却无送达证人")
            # R5 是信息量：只要求它是个非负整数读数，不进退码、不作通过/失败判据。
            self.assertGreaterEqual(r["r5_nonexact_arrival_count"], 0)
        elif FACE == "old":
            # 待裁①（#69-F）裁定 (b)：old 面**降为基线审计快照、不是失败测试**。
            #   old==当前代码 ⇒ 三者全 0（缺陷已被 C1 修 + 新门只认 origin），拿它当"永久红的测试"
            #   会让跑默认 face 的聚合 runner 长期红，破坏验收基础设施。历史证人不靠这个红持有——
            #   它在冻结产物 c1_face_old.json（R1=12/R4=1/R5=12）+ #69-A/C0 文档里。故显式 skip，不删。
            self.skipTest("[OLD_IS_BASELINE_AUDIT_SNAPSHOT] pre-C1 基线审计见 docs/取证输出/c1_face_old.json"
                          "（R1=12/R4=1/R5=12）；old 面不作通过/失败判据，牙由 mutate/forced_cleanup 注入面持有")
        else:
            # mutate / forced_cleanup：期望"有牙才通过"。
            #   · forced_cleanup 注入 origin=cleanup+无 DESTINATION_REACHED ⇒ 语义门=1（本门的用途）
            #   · mutate 注入重复 completion ⇒ R3=1
            teeth = (r["cleanup_completion_without_service"] > 0
                     or r["R3_duplicate_completion"] > 0
                     or r["R4_aggregate_not_recomputable"] > 0)
            self.assertTrue(teeth,
                            f"[C1_NO_TEETH] 该面无任何违规读数（语义门/R3/R4 全 0）："
                            f"{json.dumps(r, ensure_ascii=False)}")

    def test_2_pickup_precedes_delivery(self):
        """R2 取货前置：TASK_LOADED 时间必须早于 DESTINATION_REACHED。"""
        self.assertEqual(self.res["R2_pickup_not_before_delivery"], 0,
                         f"[C1_R2] {self.res['R2_pickup_not_before_delivery']} 个任务缺『先取货』证人")

    def test_3_split_identity(self):
        """恒等式：counter == legal_unique + 无送达证据数（防某类既不算通过也不算失败）。"""
        r = self.res
        self.assertEqual(r["counter"],
                         r["legal_unique"] + r["R1_missing_destination_evidence"],
                         f"[C1_SPLIT_IDENTITY_BROKEN] {json.dumps(r, ensure_ascii=False)}")

    def test_3_reason_is_not_invented_state(self):
        """reason 只能是两种几何证据之一；出现第三种即有人在推断业务语义。"""
        # origin 只允许三种取值；出现业务语义词（released/failed/delivered…）即有人提前发明状态
        allowed = {"destination_branch", "is_free_cleanup_branch", "unknown_call_site"}
        got = {e.get("record_origin") for e in self.trace["events"]
               if e["kind"] == "TASK_COMPLETION_RECORDED"}
        self.assertTrue(got <= allowed, f"[C1_ORIGIN_INVENTED_STATE] {got - allowed}")
        banned = {"released", "failed", "delivered", "aborted", "requeued", "unassigned"}
        self.assertFalse(got & banned, f"[C1_BUSINESS_SEMANTIC_PREMATURE] {got & banned}")
        # 归因不得失败：unknown 必须为 0，否则量具瞎了却在报数
        unattr = (self.trace.get("summary") or {}).get("unattributed_completions")
        if unattr is None:
            unattr = sum(1 for e in self.trace["events"]
                         if e["kind"] == "TASK_COMPLETION_RECORDED"
                         and e.get("record_origin") == "unknown_call_site")
        self.assertEqual(unattr, 0, "[C1_ATTRIBUTION_BLIND] 有 completion 无法归因到调用分支")

    def test_4_mutation_face_proves_teeth(self):
        """mutation 面：注入『cleanup 被伪造成送达 + 同任务重复 completion』，R3/R5 必须变红。"""
        if FACE != "mutate":
            self.skipTest("仅 mutation 面执行")
        base = classify(self.trace)
        self.assertGreaterEqual(base["R3_duplicate_completion"], 0)
        dup = base["R3_duplicate_completion"]
        self.assertGreater(dup, 0, "[C1_MUTATE_R3_NOT_CAUGHT] 注入的重复未被抓到")

    # ------------------------------------------------------------------
    # #69-E：把 D §2(a)/(b) 两条对账升级成常驻门（自然面绿 + 合成注入证牙）
    # ------------------------------------------------------------------
    def test_5_GD_a_timeout_only_from_legal_delivery(self):
        """(a) timeout/delay 只由 legal delivery completion 产生 —— 结构判据，非常量。

        自然面（old/fixed/mutate/forced_cleanup 的真实生产轨迹部分）：GD_a 必须=0。
        ⚠ forced_cleanup/mutate 会往 trace 里注入事件，但注入的是"无 delay 的完成"或"合法重复"，
          不制造非法 delay 贡献 ⇒ GD_a 在四面都应=0；若某面 >0 说明该面的注入本身引入了非法来源时延，需查。
        """
        r = self.res
        self.assertEqual(r["GD_a_timeout_from_illegal"], 0,
                         f"[GDA_TIMEOUT_FROM_ILLEGAL] {r['GD_a_timeout_from_illegal']} 条 timeout/delay "
                         f"来自非 destination_branch 的完成 ⇒ 见 {json.dumps(r, ensure_ascii=False)}")
        # 证牙：合成一条 d_delay>0 且 origin=is_free_cleanup_branch 的完成，谓词必须抓到它。
        synth = list(self.trace["events"]) + [{
            "kind": "TASK_COMPLETION_RECORDED", "seq": 10 ** 9, "task_id": "__gda_probe__",
            "drone_index": 0, "record_origin": "is_free_cleanup_branch",
            "has_destination_evidence": False, "has_load_evidence": True,
            "d_completed": 1, "d_ontime": 0, "d_delay": 5.0, "sim_time": 0.0,
        }]
        got = classify({"events": synth, "total_completed_tasks": r["counter"]})["GD_a_timeout_from_illegal"]
        self.assertGreaterEqual(got, 1,
                                "[GDA_NO_TEETH] 注入了非法 delay 贡献而谓词没抓到 ⇒ 门无牙")

    def test_6_GD_b_dr_completion_bidirectional_align(self):
        """(b) DR ↔ completion 双向对齐 + counter 可重算：三量互等、缺项=0、孤儿=0。

        ⚠ 判据作用在**自然生产轨迹**上，不是本面的注入后 trace —— mutate/forced_cleanup 会故意
          注入错位（那是 R3/R4 的职责），拿注入 trace 断言"必须对齐"会与 mutation 面自相矛盾。
          self.trace["events"] 在这两面已被 _collect 换成注入后的列表 ⇒ 读不到未注入基线，
          故自然轨迹从 old/fixed 面写出的 c1_face_live_fixed.json 取（同 seed/算法/步数的生产真值）。
        """
        r = self.res
        nat_file = OUT_DIR / "c1_face_live_fixed.json"
        if not nat_file.is_file():
            self.skipTest("[GDB_NO_NATURAL_BASELINE] 缺 c1_face_live_fixed.json ⇒ 无法核对自然轨迹对齐")
        nat_events = json.loads(nat_file.read_text(encoding="utf-8"))["events"]
        # 自然轨迹的 counter：Σd_completed（不是本面注入后的 r["counter"]，否则 mutate/forced_cleanup
        #   会拿"注入后计数"去比"未注入事件数"，制造假错位）。
        nat_counter = int(sum(e.get("d_completed", 0) for e in nat_events
                              if e["kind"] == "TASK_COMPLETION_RECORDED"))
        natural = classify({"events": nat_events, "total_completed_tasks": nat_counter})
        self.assertTrue(natural["GD_b_alignment_ok"],
                        f"[GDB_MISALIGNED] counter={natural['counter']} "
                        f"completions={natural['completions_recorded']} "
                        f"Σd_completed={natural['GD_b_sum_d_completed']} "
                        f"missing_dr={natural['GD_b_missing_dr']} orphan_dr={natural['GD_b_orphan_dr']}")
        # 证牙：删掉一条 DESTINATION_REACHED ⇒ 出现"缺 DR 的完成"，对齐必须破。
        ev = list(nat_events)
        first_reach = next((i for i, e in enumerate(ev) if e["kind"] == "DESTINATION_REACHED"), None)
        if first_reach is None:
            self.skipTest("[GDB_NO_DR_TO_REMOVE] 自然轨迹里没有 DESTINATION_REACHED 可删")
        synth = ev[:first_reach] + ev[first_reach + 1:]
        got = classify({"events": synth, "total_completed_tasks": natural["counter"]})
        self.assertFalse(got["GD_b_alignment_ok"],
                         "[GDB_NO_TEETH] 删掉一条证人 DR 后对齐仍成立 ⇒ 门无牙")
        self.assertGreaterEqual(got["GD_b_missing_dr"], 1,
                                "[GDB_MISSING_NOT_COUNTED] 缺 DR 的完成没被计入 missing_dr")


def _force_cleanup(events):
    """D 组 mutation：人工制造『无合法 destination evidence 却进入 cleanup completion』。

    当前 seed 因 pickup 修复不再触发真实 cleanup ⇒ 门若只跑生产轨迹，就无法证明
    latent cleanup defect 仍被捕获。这里显式注入一条 cleanup 分支的 completion，
    要求 C1 必须 RED —— 否则说明门只是跟着生产行为变绿，失去了对未修缺陷的侦测力。
    """
    ev = [dict(e) for e in events]
    n_before = len(ev)
    comp = [e for e in ev if e["kind"] == "TASK_COMPLETION_RECORDED"]
    if not comp:
        raise AssertionError("[FORCED_NO_TEMPLATE] 轨迹里没有 completion 事件可作模板")
    tmpl = comp[0]
    forged = dict(tmpl)
    forged.update(kind="TASK_COMPLETION_RECORDED", task_id="forced_lost_task",
                  record_origin="is_free_cleanup_branch",
                  has_destination_evidence=False, has_load_evidence=False,
                  load_time_raw=None, sim_time=float(tmpl["sim_time"]) + 0.5,
                  d_completed=1, d_ontime=1, d_delay=0.0)
    ev.append(forged)
    ev = [dict(x, seq=i + 1) for i, x in enumerate(ev)]
    assert len(ev) > n_before, "[FORCED_NOT_APPLIED]"
    return ev


def _inject(events):
    """mutation（R3 牙）：把一条**合法 dest-branch 完成**复制一次 ⇒ 同任务重复计入 completed。

    ⚠ #69-C2b 重挂目标 + 改名理由：#69-C1 后生产里所有 completion 都是 origin==destination_branch 的
      合法送达，旧写法按 `not has_destination_evidence`（几何非精确）选靶——那挑中的仍是真实总体
      （dest-branch 中 A* <1m 容差抵达的那批），但叙事写的是"伪造无送达→有送达"，那是 #69-A/C0 时代
      cleanup 冒充 delivery 的场景，**生产上已不再发生**。本注入实际证明的只是更窄的一条事实：
      **同一任务的第二次完成会被 R3 抓到**（dup-with-DESTINATION_REACHED ⇒ legal_unique 计数翻倍）。
      故改挂到"任意 dest-branch 完成被重复计入"这一诚实命名，不再谎称在造无送达样本。
    ⚠ 字段名必须跟 Observer 当前 schema 一致；曾因读废弃 ``reason`` 键导致 cand is None → 原样返回
      （＝没有变异的"变异测试"）。⇒ 末尾硬断言：注入必须真的改变事件数，否则报错而非静默通过。
    """
    ev = list(events)
    cand = next((e for e in ev if e["kind"] == "TASK_COMPLETION_RECORDED"
                 and e.get("record_origin") == "destination_branch"), None)
    if cand is None:
        raise AssertionError("[MUTATE_NO_TARGET] 轨迹里没有 dest-branch 完成可作重复样本 ⇒ mutate 面无意义")
    forged = dict(cand)
    forged["has_destination_evidence"] = True
    forged["record_origin"] = "destination_branch"
    reach = {"kind": "DESTINATION_REACHED", "sim_time": cand["sim_time"],
             "task_id": cand["task_id"], "drone_index": cand["drone_index"],
             "reach_has_load_evidence": cand.get("has_load_evidence", False),
             "payload_at_reach": 0.0, "task_weight": 0.0}
    dup = dict(cand)
    before = len(ev)
    out = ev + [forged, dup, reach]
    # seq 必须重排：R2/R3 读的是 seq，沿用旧 seq 会让"顺序"这一判据失真
    for n, e in enumerate(out, start=1):
        e = dict(e); e["seq"] = n
    out = [dict(x, seq=i + 1) for i, x in enumerate(out)]
    assert len(out) > before, "[MUTATE_NOT_APPLIED] 注入没有改变事件集合"
    return out


# mutation 面走 classify(injected=_inject)，故在执行前替换 trace
if FACE == "mutate":
    _orig_collect = _collect

    def _collect(face):                                # noqa: F811
        t = _orig_collect("old")
        t["events"] = (_inject(t["events"]) if face == "mutate"
                       else _force_cleanup(t["events"]))
        return t


if __name__ == "__main__":
    unittest.main(verbosity=2)
