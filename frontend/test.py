import os
import sys

# 让 frontend 能 import 到 backend_si
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from environment import Environment
from backend_si.pso_scheduler import PSOScheduler
from task_shower import TaskShowerManager
from greedy.scheduler import GreedyScheduler


if __name__ == "__main__":
    from task import TASK_GEN_MODE

    print("=" * 70)
    print("无人机配送调度仿真 - PSOScheduler（双通道 + 动态贪心，配置见 backend_si/config.yaml）")
    print(f"任务生成方式: {TASK_GEN_MODE}")
    print("=" * 70)

    env = Environment('data/map/part_of_yangpu.osm', visualize=True)

    # 所有可调参数读自 backend_si/config.yaml；要换实验配置传 config_path=...
    scheduler = PSOScheduler(num_drones=len(env.drones), verbose=True)
    task_shower = TaskShowerManager(update_interval=0.5)
    task_shower.start()

    frame_count = 0
    done = False
    observations = env.reset()  # 获取初始状态
    total_reward = 0.0

    while not done:
        action = scheduler.step(observations, current_time=env.current_time)
        observations, reward, done, _ = env.step(action)

        print(f"Frame: {frame_count}, Reward: {reward:.2f}")
        frame_count += 1

        task_shower.collect_and_update(env, observations)

        if frame_count % 60 == 0:
            free_drones = sum(1 for d in env.drones if d.is_free)
            busy_drones = sum(1 for d in env.drones if not d.is_free)
            queue_sizes = {i: len(q) for i, q in scheduler.drone_queues.items()}
            print(f"\n[Frame {frame_count}] Reward: {reward:.2f}, Total: {total_reward:.2f}, "
                  f"Tasks: {len(observations['unassigned_tasks'])}, "
                  f"Free: {free_drones}, Busy: {busy_drones}, "
                  f"Queues: {queue_sizes}, Buffer: {len(scheduler.pending_buffer)}")
        
        # 每300帧（约5秒）打印一次累计统计
        if frame_count > 0 and frame_count % 300 == 0:
            env.print_statistics()
        
    
    print("\n" + "=" * 70)
    print(f"仿真结束")
    print("=" * 70)
    print(f"总帧数: {frame_count}")
    print(f"总奖励: {total_reward:.2f}")
    print("=" * 70)
    
    # 打印最终统计
    env.print_statistics()

    print("=" * 70)
    print("调度器事件统计")
    print("=" * 70)
    for k, v in scheduler.get_stats().items():
        print(f"  {k}: {v}")
    print("=" * 70)

    task_shower.stop()