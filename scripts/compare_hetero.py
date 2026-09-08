"""异构 vs 同质机队 A/B 对比脚本。

用法（每次进程只跑一种模式，由外部连续调用两次完成对比）：
    python compare_hetero.py --mode hetero --episodes 3 --seed 100
    python compare_hetero.py --mode homo   --episodes 3 --seed 100

说明：
    drone.py / environment.py 在 import 时缓存 heterogeneous.enabled，因此
    本脚本在导入 environment 前按 --mode 写入 simulation.json，保证同进程内
    机型开关一致。对比两种模式时务必使用相同 --seed，保证任务生成公平。
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "simulation"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SIMULATION_ROOT))

CFG_PATH = PROJECT_ROOT / "config" / "simulation.json"


def set_hetero_enabled(enabled):
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    cfg.setdefault("heterogeneous", {})["enabled"] = bool(enabled)
    CFG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


METRIC_KEYS = [
    "completion_rate",
    "on_time_rate",
    "timeout_rate",
    "avg_delay",
    "avg_wait_time_to_load",
    "avg_delivery_time",
    "avg_generation_to_completion_time",
    "avg_energy_per_task",
    "total_energy_consumed",
    "total_completed",
    "total_generated",
]


def _to_row(mode, episode, stats):
    row = {"mode": mode, "episode": episode}
    for k in METRIC_KEYS:
        row[k] = float(stats.get(k, 0.0))
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["hetero", "homo"])
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--episode-steps", type=int, default=None)
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--osm", type=str, default="data/map/part_of_yangpu.osm")
    args = parser.parse_args()

    set_hetero_enabled(args.mode == "hetero")

    # 切好开关后再导入，确保机型参数与观察空间一致
    from simulation.environment import Environment
    from scheduling.greedy.scheduler import greedy_action_from_observation

    episode_steps = args.episode_steps or 2000
    mode_label = "heterogeneous" if args.mode == "hetero" else "homogeneous"

    out_csv = PROJECT_ROOT / "results" / "compare" / f"hetero_vs_homo_{args.mode}.csv"
    rows = []

    for ep in range(args.episodes):
        seed = args.seed + ep
        env = Environment(str(FRONTEND_ROOT / args.osm), visualize=False,
                          episode_max_steps=episode_steps)
        obs = env.reset(seed=seed)

        # 记录每类机型承接任务的频次（分配口径）
        type_assignment = Counter()
        done = False
        while not done:
            action = greedy_action_from_observation(obs)
            for drone_idx, task_ids in action.items():
                if task_ids:
                    dtype = env.drones[drone_idx].drone_type or "homogeneous"
                    type_assignment[dtype] += len(task_ids)
            obs, _, done, _ = env.step(action)

        stats = env.get_statistics()
        stats["episode_step"] = int(env.current_time)
        rows.append(_to_row(mode_label, ep + 1, stats))

        print(f"[{mode_label}] ep{ep + 1} seed={seed} | "
              f"完成率={stats['completion_rate']:.3f} "
              f"准时率={stats['on_time_rate']:.3f} "
              f"平均时延={stats['avg_delay']:.2f} "
              f"完成={stats['total_completed']}/{stats['total_generated']} | "
              f"机型接单频次={dict(type_assignment)}")

    # 写每回合明细
    header = ["mode", "episode"] + METRIC_KEYS
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([r[h] for h in header])

    # 打印均值摘要
    n = len(rows)
    print("\n" + "=" * 68)
    print(f"{mode_label} 均值汇总 (episodes={n})")
    print("=" * 68)
    means = {k: sum(r[k] for r in rows) / n for k in METRIC_KEYS}
    for k in METRIC_KEYS:
        print(f"  {k:32s} {means[k]:.4f}")
    print(f"  csv_file: {out_csv}")
    print("=" * 68)


if __name__ == "__main__":
    main()