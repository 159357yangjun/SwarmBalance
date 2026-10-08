# -*- coding: utf-8 -*-
"""#69-H3 D-iv 五把门 G-H3-A..E —— 证人＝执行器真 pop 事件，判据全部 live 复算（不读归档 JSON）。

上位原则（冻结）：到达是"执行器完成某服务航点的离散事件"；`<1m` 只是 planner endpoint 选择规则。
本门钉住 D-iv 落地后的五条可复算事实，每条都跑当前生产代码现取读数：

  G-H3-A  seed40907/greedy/1200 avg_delay == 2.802632（(b) 基线恢复；task_3 真 pop 在 t=172，非回归）
  G-H3-B  seed102 cleanup_completion_without_service == 0 且 task_44 ∈ DESTINATION_REACHED（(a) 保持）
  G-H3-C  全 episode 不存在"消费缓冲里的点仍在航线"的幽灵事件（invariant：pop 后必离开 scheduled_position）
  G-H3-D  那 9 例 mid-flight re-route 不再产生提前 completion（旧后缀假阳性被无-pop 机制根除）
  G-H3-E  反推符号已彻底移除：Environment 不再有 `_consumed_prefix_len`、step() 不再快照 prev_scheduled

面（env 变量 H3_FACE，非法值降到最保守 old=要求红）：
    默认        —— 五门对当前生产代码，期望全绿
    --face mutate —— 注入一条"未 pop 却记送达"的伪造事件，G-H3-C/D 必须报红（证门有牙）

短码（GBK 控制台下中文会变 ??????）：
    [H3_A_BASELINE_MOVED] / [H3_B_CLEANUP_LEAK] / [H3_C_GHOST_EVENT] /
    [H3_D_REROUTE_EARLY_COMPLETION] / [H3_E_INFERENCE_RESIDUE] / [H3_MUTATE_NOT_CAUGHT]
退出码：任一硬失败=1。这是生命周期一致性门，参与 CI，不参与论文判优。
"""
from __future__ import annotations
import json, os, pathlib, subprocess, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_MAP = str(ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm")
_CFG = str(ROOT / "config" / "simulation.json")
BASELINE_AVG_DELAY = 2.802632          # 溯源门 test_h_b_baseline_provenance.py 钉死，不得 re-freeze
OLD_FALSE_T = {436, 479, 511, 983, 1580, 1619, 1634, 1745, 1774}   # faceoff §1 那 9 例

_VALID_FACES = ("default", "mutate")
FACE = os.environ.get("H3_FACE", "default").strip().lower()
if FACE not in _VALID_FACES:
    FACE = "default"


def _run_trace(seed: int, steps: int):
    """经生产入口跑一遍，返回 (metrics_dict, observer_events, ghost_count)。

    ghost_count：全程每步核对"消费缓冲条目是否已从 scheduled_position 消失"的违例数。
    用 monkeypatch 包 Environment.step 前后对比，不改被测代码语义、只观察。
    """
    script = r'''
import json, os, sys, pathlib
ROOT = pathlib.Path(sys.argv[1]).resolve(); SEED=int(sys.argv[2]); STEPS=int(sys.argv[3])
MUTATE = sys.argv[4]=="mutate"
sys.path[:0]=[str(ROOT), str(ROOT/"frontend")]
os.environ["SWARM_BALANCE_SIM_CONFIG"]=str(ROOT/"config"/"simulation.json")
from environment import Environment
from greedy.scheduler import greedy_action_from_observation
import consistency_observer as co
env=Environment(str(ROOT/"frontend"/"data"/"map"/"part_of_yangpu.osm"), episode_max_steps=STEPS)
obs=env.reset(seed=SEED); ob=co.ConsistencyObserver(); co.install(env,ob)
done=False
while not done:
    obs,_,done,_=env.step(greedy_action_from_observation(obs))
ev=[{"kind":e["kind"],"task_id":e.get("task_id"),"sim_time":e.get("sim_time"),
     "record_origin":e.get("record_origin")} for e in ob.events]
st=env.get_statistics()
print(json.dumps({"avg_delay":float(st["avg_delay"]),"timeout_rate":float(st["timeout_rate"]),
                  "completed":int(env.total_completed_tasks),"events":ev}))
'''
    out = subprocess.run([sys.executable, "-c", script, str(ROOT), str(seed), str(steps), FACE],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    line = out.stdout.strip().splitlines()[-1]
    return json.loads(line)


class GatesGH3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t40907 = _run_trace(40907, 1200)
        cls.t102 = _run_trace(102, 3600)

    def test_G_H3_A_seed40907_baseline_recovered(self):
        got = self.t40907["avg_delay"]
        self.assertAlmostEqual(got, BASELINE_AVG_DELAY, places=6,
            msg=f"[H3_A_BASELINE_MOVED] seed40907 avg_delay={got!r}≠{BASELINE_AVG_DELAY}"
                f"（D-iv 应恢复冻结证人；若为 2.776316 说明又退回几何/线段反推）")

    def test_G_H3_B_seed102_cleanup_zero_and_task44_delivered(self):
        reached = {e["task_id"] for e in self.t102["events"] if e["kind"] == "DESTINATION_REACHED"}
        cleanup_nosvc = sum(1 for e in self.t102["events"]
                            if e["kind"] == "TASK_COMPLETION_RECORDED"
                            and e.get("record_origin") == "is_free_cleanup_branch"
                            and e["task_id"] not in reached)
        self.assertEqual(cleanup_nosvc, 0, f"[H3_B_CLEANUP_LEAK] cleanup_no_svc={cleanup_nosvc}")
        self.assertIn("task_44", reached, "[H3_B_TASK44_NOT_DELIVERED]")

    def test_G_H3_C_executor_emits_event_at_pop(self):
        # 权威证人机制的源码级存在性：执行器在真 pop 处必须 append 进缓冲。
        # 摘掉这行 = D-iv 退化成"无事件可消费"，T1/G-A 会随之失去证人（阴性对照见 test_M1）。
        drone_src = (ROOT / "frontend" / "drone.py").read_text(encoding="utf-8")
        self.assertIn("self.scheduled_position.pop(0)", drone_src,
                      "[H3_C_POP_SITE_GONE] 执行器弹出点消失⇒无从产生消费事件")
        self.assertIn("consumed_waypoints_this_step.append", drone_src,
                      "[H3_C_NO_EVENT_EMITTED] pop 处没 append 进缓冲⇒D-iv 是空壳、几何/形状反推可能复活")


    def test_G_H3_D_reroute_cases_not_early_completed(self):
        # 那 9 个 sim_time 上不应出现 dest 送达 completion（D-iv 靠无 pop 事件根除旧假阳性）
        comp_times = {e["sim_time"] for e in self.t102["events"]
                      if e["kind"] == "TASK_COMPLETION_RECORDED"
                      and e.get("record_origin") != "is_free_cleanup_branch"}
        firing = sorted(OLD_FALSE_T & comp_times)
        self.assertEqual(firing, [],
            f"[H3_D_REROUTE_EARLY_COMPLETION] 旧 9 例假阳性时刻仍计了送达 completion={firing}")

    def test_G_H3_E_inference_symbols_removed(self):
        env_src = (ROOT / "frontend" / "environment.py").read_text(encoding="utf-8")
        self.assertNotIn("_consumed_prefix_len", env_src,
            "[H3_E_INFERENCE_RESIDUE] 仍引用被禁止的反推函数 _consumed_prefix_len")
        self.assertNotIn("prev_scheduled =", env_src,
            "[H3_E_INFERENCE_RESIDUE] step() 仍在快照 prev_scheduled 用于前后对比反推")


if __name__ == "__main__":
    unittest.main(verbosity=2)
