"""单次 episode 的隔离执行进程。

由 :mod:`experiments.runner` 调用。每个进程只加载一个 simulation.json，因此
frontend 中的模块级配置常量不会在不同实验条件之间串值。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def _build_scheduler(policy: str, env, seed: int):
    if policy == "greedy":
        return None
    if policy == "pso":
        from backend_si.pso_scheduler import PSOScheduler
        return PSOScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    if policy == "ga":
        from backend_si.ga_scheduler import GAScheduler
        return GAScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    if policy == "ortools":
        from backend_si.ortools_scheduler import ORToolsScheduler, ORTOOLS_AVAILABLE
        if not ORTOOLS_AVAILABLE:
            raise RuntimeError("OR-Tools 未安装：pip install ortools")
        return ORToolsScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    raise ValueError(f"未知算法: {policy}")


def run_one(config_path: Path, algorithm: str, seed: int, episode_steps: int, osm_path: Path):
    # 必须在导入 environment / drone / task 之前设置。
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(config_path.resolve())
    for p in (str(PROJECT_ROOT), str(FRONTEND_ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)

    from environment import Environment
    from metrics_schema import to_output_metrics

    env = Environment(str(osm_path), episode_max_steps=int(episode_steps))
    obs = env.reset(seed=int(seed))
    scheduler = _build_scheduler(algorithm, env, int(seed))

    if algorithm == "greedy":
        from greedy.scheduler import greedy_action_from_observation

    done = False
    while not done:
        if algorithm == "greedy":
            action = greedy_action_from_observation(obs)
        else:
            action = scheduler.step(obs, current_time=env.current_time)
        obs, _, done, _ = env.step(action)

    stats = env.get_statistics()
    stats["episode_step"] = int(env.current_time)
    result = {
        "ok": True,
        "algorithm": algorithm,
        "seed": int(seed),
        "episode_steps": int(episode_steps),
        "metrics": to_output_metrics(stats),
        "scheduler_stats": scheduler.get_stats() if scheduler is not None and hasattr(scheduler, "get_stats") else {},
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="SwarmBalance isolated experiment worker")
    parser.add_argument("--config", required=True)
    parser.add_argument("--algorithm", required=True, choices=["greedy", "pso", "ga", "ortools"])
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--episode-steps", required=True, type=int)
    parser.add_argument("--osm", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        result = run_one(Path(args.config), args.algorithm, args.seed, args.episode_steps, Path(args.osm))
    except Exception as exc:  # worker 失败要落盘，主编排器继续跑其他组合
        result = {
            "ok": False,
            "algorithm": args.algorithm,
            "seed": args.seed,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "metrics": {},
        }
    result["duration_seconds"] = round(time.perf_counter() - started, 4)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
