# -*- coding: utf-8 -*-
"""#68-B 验收门：ConsistencyObserver 启用 vs 关闭的**零漂移**双跑。

判据（用户裁定的原话拆解）：固定 seed=40907 / greedy / 1200，比较
  ① 正式 KPI（metrics_schema 全字段）
  ② action/assignment sequence（每步喂给 env.step 的 actions 与返回的 done/info）
  ③ generated task IDs（含顺序）
  ④ total_completed_tasks
  ⑤ energy（total_energy_consumed）
  ⑥ swap（换电次数）
  ⑦ steps（episode_step）
全部必须逐位相同。任何一项不同 ⇒ Observer 就不是只读，本任务作废重来。

第二组断言证明"轨迹确实有内容且能对上旧实现"（否则零漂移可能只是"啥也没记"）：
  completions_recorded == total_completed_tasks == KPI 完成任务数
  with + without delivery_evidence == completions_recorded   （恒等式，防某类既不算通过也不算失败）
  rejected_event_names == []                                  （本模块不许发明状态事件名）

两面原始输出都落盘成文件（口头"跑过了"不可复算）。
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

# CHECKER-BIND: 本门只依赖 frontend/consistency_observer.py 与 experiments/worker.py，二者同仓。

_RUNNER = r'''
import json, os, pathlib, sys
ROOT = pathlib.Path(sys.argv[2]).resolve()
sys.path[:0] = [str(ROOT), str(ROOT / "frontend")]
os.environ["SWARM_BALANCE_SIM_CONFIG"] = str((ROOT / "config" / "simulation.json").resolve())
from environment import Environment
from metrics_schema import to_output_metrics
from greedy.scheduler import greedy_action_from_observation
import consistency_observer as co

observer = co.ConsistencyObserver() if sys.argv[1] == "on" else None
env = Environment(str(ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm"),
                  episode_max_steps=int(%(steps)d))
obs = env.reset(seed=int(%(seed)d))
if observer is not None:
    co.install(env, observer)

seq, gen_ids = [], []
seen = set()
done = False
while not done:
    action = greedy_action_from_observation(obs)
    seq.append({"t": int(env.current_time),
                "action": {str(k): list(v) for k, v in sorted((action or {}).items())}})
    obs, rew, done, info = env.step(action)
    for tid in (info.get("new_task_ids") or []):
        if tid not in seen:
            seen.add(tid); gen_ids.append(tid)
    if len(seq) > %(cap)d:
        raise RuntimeError("episode did not terminate within cap")

stats = env.get_statistics()
payload = {
    "mode": sys.argv[1],
    "kpi": to_output_metrics(stats),
    "raw_total_completed": int(env.total_completed_tasks),
    "raw_total_energy": float(stats.get("total_energy_consumed", 0.0)),
    "raw_swap": int(stats.get("total_battery_swaps", stats.get("swap_count", 0))),
    "episode_step": int(env.current_time),
    "sequence_len": len(seq),
    "sequence_sha": __import__("hashlib").sha256(
        json.dumps(seq, sort_keys=True).encode()).hexdigest(),
    "sequence": seq,
    "generated_task_ids": gen_ids,
}
if observer is not None:
    payload["observer_summary"] = observer.summary()
    payload["observer_events"] = observer.events
print(json.dumps(payload, ensure_ascii=False))
''' % {"seed": SEED, "steps": STEPS, "cap": STEPS * 3}


def _run(mode: str, tmpdir: pathlib.Path) -> dict:
    script = tmpdir / f"runner_{mode}.py"
    script.write_text(_RUNNER, encoding="utf-8")
    proc = subprocess.run([sys.executable, str(script), mode, str(ROOT)],
                          capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        raise AssertionError(f"[OBSERVER_RUN_FAILED] mode={mode} rc={proc.returncode}\n"
                             f"{proc.stdout[-1500:]}\n{proc.stderr[-2500:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


class ObserverZeroDrift(unittest.TestCase):
    """零漂移是主判据；轨迹非空 + 对账是它没空转的证据。"""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            cls.off = _run("off", tmp)
            cls.on = _run("on", tmp)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for mode, payload in (("off", cls.off), ("on", cls.on)):
            (OUT_DIR / f"observer_zero_drift_{mode}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------- ① 正式 KPI ----------------
    def test_a_kpi_identical(self):
        self.assertEqual(self.off["kpi"], self.on["kpi"], "[ZERO_DRIFT_KPI]")

    # ---------------- ② action/assignment sequence ----------------
    def test_b_sequence_identical(self):
        self.assertEqual(self.off["sequence_sha"], self.on["sequence_sha"], "[ZERO_DRIFT_SEQUENCE]")
        self.assertEqual(self.off["sequence"], self.on["sequence"], "[ZERO_DRIFT_SEQUENCE_BODY]")
        self.assertEqual(self.off["sequence_len"], self.on["sequence_len"])

    # ---------------- ③ generated task ids ----------------
    def test_c_generated_ids_identical(self):
        self.assertEqual(self.off["generated_task_ids"], self.on["generated_task_ids"],
                         "[ZERO_DRIFT_TASK_IDS]")

    # ---------------- ④⑤⑥⑦ 计数 / 能耗 / 换电 / 步数 ----------------
    def test_d_counters_energy_swap_steps(self):
        for key in ("raw_total_completed", "raw_total_energy", "raw_swap", "episode_step"):
            self.assertEqual(self.off[key], self.on[key], f"[ZERO_DRIFT_{key.upper()}]")

    # ---------------- 轨迹确有内容，且与旧实现对上 ----------------
    def test_e_trace_not_empty_and_reconciles(self):
        s = self.on["observer_summary"]
        self.assertGreater(s["events_total"], 0, "[OBSERVER_DID_NOT_RECORD_ANYTHING]")
        self.assertEqual(s["completions_recorded"], self.on["raw_total_completed"],
                         "[RECONCILE_COMPLETION_VS_COUNTER]")
        self.assertEqual(s["completions_recorded"], self.off["kpi"].get("完成任务数",
                         self.off["kpi"].get("completed_tasks")),
                         "[RECONCILE_COMPLETION_VS_KPI]")
        # 恒等式：两类证据之和必须等于总数，否则某类既不算通过也不算失败
        self.assertEqual(s["legal_completions"] + s["illegal_completions_no_destination_evidence"],
                         s["completions_recorded"], "[EVIDENCE_SPLIT_IDENTITY]")

    def test_f_no_invented_state_events(self):
        """白名单自证：出现任何未登记事件名 ⇒ 有人在往轨迹里塞推断状态。"""
        self.assertEqual(self.on["observer_summary"]["rejected_event_names"], [],
                         "[OBSERVER_INVENTED_EVENT]")

    def test_g_completion_reasoning_is_fact_based(self):
        """无送达证据的 completion 必须存在且带原始 load_time —— 这是 C1 门的正例来源。"""
        s = self.on["observer_summary"]
        self.assertGreater(s["illegal_completions_no_destination_evidence"], 0,
                           "[NO_POSITIVE_CASE_FOR_C1] 若为 0 则本门无从判定")
        bad = [e for e in self.on["observer_events"]
               if e["kind"] == "TASK_COMPLETION_RECORDED" and not e["has_destination_evidence"]]
        self.assertTrue(all(e["sim_time"] >= 0 for e in bad))
        # 每条都要能追溯到一次真实计数增量
        self.assertEqual(sum(e["d_completed"] for e in bad), len(bad),
                         "[DELTA_PER_EVENT_MUST_BE_ONE]")

    def test_h_attribution_matches_frozen_baseline(self):
        """归因互核只对**冻结基线代码**有意义。

        dest=26 / cleanup=12 / never_loaded=3 / without_load=7 是 commit 580c937 的行为。
        #69-B 修 source pickup 语义后这些数本就该变（never_loaded 3→0 正是修复效果），
        拿它们断言当前工作树会把"修好了"报成"量具坏了" —— 归因方向错。
        ⇒ 仅当 C1_BASELINE_SHA=580c937（被测代码即冻结基线）时断言，否则跳过并说明。
        """
        s = self.on["observer_summary"]
        if os.environ.get("C1_BASELINE_SHA", "") != "580c937":
            self.skipTest("[H_SKIPPED_NOT_FROZEN_BASELINE] 该基准只对 580c937 有效；"
                          "修复后行为请见 c1_face_r2_fixed.json")
        BASELINE = {"legal_completions": 26,
                    "illegal_completions_no_destination_evidence": 12,
                    "illegal_and_never_loaded": 3,
                    "destination_without_load": 7}
        for k, v in BASELINE.items():
            self.assertEqual(s[k], v, f"[ATTRIBUTION_DRIFT {k}] got={s[k]} want={v}")
        self.assertEqual(s["unattributed_completions"], 0, "[ATTRIBUTION_BLIND]")
        self.assertEqual(s["completion_origins"].get("destination_branch"), 26, "[ORIGIN_DEST_COUNT]")
        self.assertEqual(s["completion_origins"].get("is_free_cleanup_branch"), 12, "[ORIGIN_CLEANUP_COUNT]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
