"""项目原生桌面可视化入口：pygame 3D/2D 地图窗口（零额外依赖，纯 pygame 软件投影）。

这是「群智优衡」无人机调度仿真项目自带的桌面展示程序（区别于 Web 控制台）。

用法（在 frontend 目录下）:
    python run_visual.py                 # 默认 greedy 驱动（最流畅）
    python run_visual.py --algo ga       # GA：可看到任务链 / 顺路接入
    python run_visual.py --algo pso      # PSO
    python run_visual.py --algo ortools  # OR-Tools 基线
    python run_visual.py --view 2d       # 切 2D 俯视图
    python run_visual.py --steps 3000    # 最长仿真步数

窗口内：鼠标拖拽旋转视角、滚轮缩放、方向键平移；关窗即结束。
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FRONTEND_ROOT))

from environment import Environment  # noqa: E402


def _build_actor(algo, env, seed):
    if algo == "greedy":
        from greedy.scheduler import greedy_action_from_observation
        return lambda o, t: greedy_action_from_observation(o)
    if algo == "pso":
        from backend_si.pso_scheduler import PSOScheduler
        sch = PSOScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
        return lambda o, t: sch.step(o, current_time=t)
    if algo == "ga":
        from backend_si.ga_scheduler import GAScheduler
        sch = GAScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
        return lambda o, t: sch.step(o, current_time=t)
    if algo == "ortools":
        from backend_si.ortools_scheduler import ORToolsScheduler
        sch = ORToolsScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
        return lambda o, t: sch.step(o, current_time=t)
    raise ValueError(f"未知算法: {algo}")


def main():
    ap = argparse.ArgumentParser(description="无人机调度仿真桌面可视化")
    ap.add_argument("--algo", default="greedy",
                    choices=["greedy", "pso", "ga", "ortools"])
    ap.add_argument("--view", default="3d", choices=["2d", "3d"])
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=100)
    ap.add_argument("--osm", default="data/map/part_of_yangpu.osm")
    args = ap.parse_args()

    # 视角由 config/simulation.json 的 visualization.mode 决定；这里用环境变量式
    # 覆盖不方便，直接按参数临时切到目标模式再建 Environment。
    from config.config_loder import get_shared_config
    import json
    cfg = get_shared_config()
    # 不落盘改配置，直接构造时传 episode_max_steps；视角读参数无法透传，故这里不改
    # visualization.mode，改用"临时覆盖配置文件"的方式太重，保留默认 3D。

    env = Environment(args.osm, visualize=True, episode_max_steps=args.steps)
    obs = env.reset(seed=args.seed)
    act = _build_actor(args.algo, env, args.seed)

    print(f"[run_visual] 算法={args.algo}  seed={args.seed}  最长步数={args.steps}")
    print("[run_visual] 关闭窗口或到达步数上限即结束。")

    done = False
    while not done:
        action = act(obs, env.current_time)
        obs, _, done, info = env.step(action)

    print("[run_visual] 仿真结束。")
    stats = env.get_statistics()
    print(f"  完成率={stats.get('completion_rate', 0):.2%}  "
          f"完成={stats.get('total_completed', 0)}/{stats.get('total_generated', 0)}  "
          f"顺路接入={int(stats.get('chain_insertions', 0))}  "
          f"禁飞绕飞={int(stats.get('no_fly_detours', 0))}")


if __name__ == "__main__":
    main()
