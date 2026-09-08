"""验证异构匹配度是否按机型合理分工。

统计每类机型实际承接任务的平均重量/体积/超时情况，
用于确认"能力-需求匹配度函数"确实引导合适任务流向合适机型。
"""
import os
import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from simulation.environment import Environment
from scheduling.greedy.scheduler import greedy_action_from_observation


def main():
    env = Environment("data/map/part_of_yangpu.osm", visualize=False, episode_max_steps=2000)
    obs = env.reset()

    # 记录每类机型承接的任务属性
    type_stats = defaultdict(lambda: {"count": 0, "weight": 0.0, "volume": 0.0,
                                      "delay": 0.0, "on_time": 0})

    done = False
    while not done:
        action = greedy_action_from_observation(obs)
        # 记录本次分配：动作里每个 drone 接的任务
        for drone_idx, task_ids in action.items():
            dtype = env.drones[drone_idx].drone_type or "homogeneous"
            for tid in task_ids:
                for t in env.task_generator.unassigned_tasks:
                    if t.task_id == tid:
                        type_stats[dtype]["count"] += 1
                        type_stats[dtype]["weight"] += t.get_weight()
                        type_stats[dtype]["volume"] += t.get_volume()
                        break
        obs, _, done, info = env.step(action)

    # 汇总任务完成延迟，按完成无人机类型统计
    for i, drone in enumerate(env.drones):
        dtype = drone.drone_type or "homogeneous"

    print("\n" + "=" * 60)
    print("机型分工统计（承接任务的平均属性）")
    print("=" * 60)
    for dtype, s in sorted(type_stats.items()):
        n = s["count"] if s["count"] else 1
        print(f"  {dtype:12s} 任务数={s['count']:3d}  "
              f"平均重量={s['weight']/n:.2f}kg  平均体积={s['volume']/n:.2f}m^3")
    print("=" * 60)

    # 机型清单
    print("\n机队构成：")
    from collections import Counter
    for dtype, cnt in Counter(d.drone_type for d in env.drones).items():
        print(f"  {dtype or 'homogeneous'}: {cnt} 架")
    print("=" * 60)


if __name__ == "__main__":
    main()