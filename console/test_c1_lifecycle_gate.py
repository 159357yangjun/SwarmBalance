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
_VALID_FACES = ("old", "fixed", "mutate")
FACE = os.environ.get("C1_FACE", "old").strip().lower()
if FACE not in _VALID_FACES:
    FACE = "old"
FIXED_TRACE = OUT_DIR / "c1_fixed_baseline_trace.json"   # 修复后由同脚本重生成


def _collect(face: str) -> dict:
    """跑一局生产仿真取轨迹；face=fixed 时读已归档的修复基线（修复落地前不存在 ⇒ 该面 skip 并点名原因）。"""
    if face == "fixed":
        if not FIXED_TRACE.is_file():
            raise unittest.SkipTest("[FIXED_FACE_UNAVAILABLE] lifecycle 修复尚未落地，"
                                    f"缺 {FIXED_TRACE}；此面按规矩记『未跑』而非通过")
        return json.loads(FIXED_TRACE.read_text(encoding="utf-8"))
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
                              capture_output=True, text=True, timeout=1800)
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

    # R1 合法完成证据：计入 completed 必须有 DESTINATION_REACHED
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

    # R5 cleanup 不得冒充 delivery：**走了 is_free_cleanup 分支、却没有送达几何证据**却计入 completed。
    # ⚠ 判据不能写成「record_origin != destination_branch」—— 那会把 26 条合法 dest 完成也判违规
    #   （本轮实测踩过：R5 一度=38）。origin 只说明代码走了哪条分支，是否算送达由几何证据定。
    r5 = [e for e in comp if not e["has_destination_evidence"]]

    return {
        "completions_recorded": len(comp),
        "counter": counter,
        "legal_unique": legal_unique,
        "R1_missing_destination_evidence": len(r1),
        "R2_pickup_not_before_delivery": len(r2),
        "R3_duplicate_completion": len(r3),
        "R4_aggregate_not_recomputable": 1 if r4 else 0,
        "R5_cleanup_counted_as_delivery": len(r5),
        "R5_never_loaded_among_them": sum(1 for e in r5
                                          if not e.get("has_load_evidence", False)),
    }


class C1LifecycleGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace = _collect(FACE)
        cls.res = classify(cls.trace)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        assert FACE in _VALID_FACES, f"[C1_BAD_FACE] {FACE}"
        (OUT_DIR / f"c1_face_{FACE}.json").write_text(
            json.dumps({"face": FACE, "verdict": cls.res, "events": cls.trace["events"]},
                       ensure_ascii=False, indent=1), encoding="utf-8")

    def test_0_event_kinds_are_the_observed_set(self):
        """断言读实测集合：DESTINATION_REACHED 必须真的出现过（#68-B 曾只在白名单里声明）。"""
        kinds = self.trace["summary"]["event_kinds_observed"]
        self.assertIn("DESTINATION_REACHED", kinds, "[C1_NO_DELIVERY_WITNESS]")

    def test_1_rules_are_enforced(self):
        """五条规则逐条断言。old 面必然在 R1/R4/R5 上红 —— 那才是本门的用途。"""
        r = self.res
        print(f"[C1 VERDICT face={FACE}] {json.dumps(r, ensure_ascii=False)}")
        if FACE == "fixed":
            expect_zero = ("R1_missing_destination_evidence", "R3_duplicate_completion",
                           "R4_aggregate_not_recomputable", "R5_cleanup_counted_as_delivery")
            for k in expect_zero:
                self.assertEqual(r[k], 0, f"[C1_FIXED_STILL_RED {k}] got={r[k]}")
        else:
            # R1：计入 completed 的每条都必须有 DESTINATION_REACHED 证人
            self.assertEqual(r["R1_missing_destination_evidence"], 0,
                             f"[C1_R1] {r['R1_missing_destination_evidence']} 条 completion 无送达证据")
            # R3：合法 completion 必须唯一
            self.assertEqual(r["R3_duplicate_completion"], 0, f"[C1_R3] {r['R3_duplicate_completion']} 个任务重复完成")
            # R4：聚合计数器必须能由无截断轨迹里的**合法** completion 重算
            self.assertEqual(r["R4_aggregate_not_recomputable"], 0,
                             f"[C1_R4] counter={r['counter']} != legal_unique={r['legal_unique']}")
            # R5：cleanup / 无送达不得冒充 delivery
            self.assertEqual(r["R5_cleanup_counted_as_delivery"], 0,
                             f"[C1_R5] {r['R5_cleanup_counted_as_delivery']} 条无送达证据却计入 completed"
                             f"（其中 {r['R5_never_loaded_among_them']} 条从未取货）")

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
        self.assertEqual(self.trace["summary"]["unattributed_completions"], 0,
                         "[C1_ATTRIBUTION_BLIND] 有 completion 无法归因到调用分支")

    def test_4_mutation_face_proves_teeth(self):
        """mutation 面：注入『cleanup 被伪造成送达 + 同任务重复 completion』，R3/R5 必须变红。"""
        if FACE != "mutate":
            self.skipTest("仅 mutation 面执行")
        base = classify(self.trace)
        self.assertGreaterEqual(base["R3_duplicate_completion"], 0)
        dup = base["R3_duplicate_completion"]
        self.assertGreater(dup, 0, "[C1_MUTATE_R3_NOT_CAUGHT] 注入的重复未被抓到")


def _inject(events):
    """mutation：把一条无送达证据的 completion 复制并伪造成有送达，且同任务重复一次。

    ⚠ 字段名必须跟 Observer 当前 schema 一致。本函数曾长期读**已废弃的 ``reason`` 键**，
    导致 ``cand is None`` → 原样返回、mutate 面与 old 面读数完全相同（＝没有变异的"变异测试"）。
    ⇒ 现在末尾有一条硬断言：**注入必须真的改变事件数**，否则当场报错而不是静默通过。
    """
    ev = list(events)
    cand = next((e for e in ev if e["kind"] == "TASK_COMPLETION_RECORDED"
                 and not e.get("has_destination_evidence", True)), None)
    if cand is None:
        raise AssertionError("[MUTATE_NO_TARGET] 轨迹里没有『无送达证据』的 completion，"
                             "无法构造伪造样本 ⇒ mutate 面无意义")
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
        t["events"] = _inject(t["events"])
        return t


if __name__ == "__main__":
    unittest.main(verbosity=2)
