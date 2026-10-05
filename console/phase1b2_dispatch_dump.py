# -*- coding: utf-8 -*-
"""D2 探针：把一个 episode 的【逐步派单事件】落盘，供两面逐行 diff。

用法：python console/phase1b2_dispatch_dump.py <权重> <provider> <fixture> <seed> <输出路径>

为什么单独一个可执行文件而不是塞进测试里：REACH_WEIGHT 与 provider 都在 import 期冻结，
每个取值必须起一个干净进程 —— 这与 worker/1B-1 是同一个约束。
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "frontend"))

OSM = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"
FIXTURES = {
    "C1": {"interval_scale": 0.70, "num_drones": 6,
           "mix": {"light_express": 3, "standard_cargo": 2, "heavy_cargo": 1}},
    "C2": {"interval_scale": 0.55, "num_drones": 4,
           "mix": {"light_express": 2, "standard_cargo": 1, "heavy_cargo": 1}},
}


def main():
    weight, provider, fixture, seed, out_path = sys.argv[1:6]
    os.environ["SWARM_BALANCE_REACH_WEIGHT"] = weight
    os.environ["SWARM_BALANCE_ROUTE_COST"] = provider
    cfg = json.loads((REPO / "config" / "simulation.json").read_text(encoding="utf-8"))
    p = FIXTURES[fixture]
    cfg["task_generation"]["realistic"].update({"interval_scale": p["interval_scale"],
                                                "total_tasks": 240})
    cfg["environment"]["num_drones"] = p["num_drones"]
    cfg["heterogeneous"]["fleet_mix"] = p["mix"]
    wd = pathlib.Path(tempfile.mkdtemp(prefix="p2dump_"))
    f = wd / "s.json"
    f.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(f)
    try:
        from environment import Environment
        from greedy.scheduler import greedy_action_from_observation, REACH_WEIGHT
        env = Environment(str(OSM), episode_max_steps=3600)
        o = env.reset(seed=int(seed))
        assert env.route_cost_kind == provider, "[PROVIDER_NOT_APPLIED] %s" % env.route_cost_kind
        lines, steps, done = [], 0, False
        while not done and steps < 3600:
            a = greedy_action_from_observation(o)
            for d, tids in sorted(a.items()):
                lines.append("%d\t%d\t%s" % (steps, d, ",".join(sorted(tids))))
            o, _, done, _ = env.step(a)
            steps += 1
        st = env.get_statistics()
        header = ("# w=%r provider=%s eta_calls=%s completed=%d timeout=%.4f n_events=%d"
                  % (REACH_WEIGHT, env.route_cost_kind,
                     env.route_cost_provider.stats().get("eta_calls"),
                     st["total_completed"], st["timeout_rate"], len(lines)))
        pathlib.Path(out_path).write_text(header + "\n" + "\n".join(lines), encoding="utf-8")
        print(header)
        return 0
    finally:
        shutil.rmtree(wd, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
