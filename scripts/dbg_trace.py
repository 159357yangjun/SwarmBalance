import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "simulation"))

import scheduling.pso_scheduler as ps
from matching import compute_match
from simulation.environment import Environment

print("_compute_match is None:", ps._compute_match is None)

env = Environment(str(PROJECT_ROOT / "simulation" / "data" / "map" / "part_of_yangpu.osm"),
                  visualize=False, episode_max_steps=2000)
obs = env.reset(seed=101)

caps = obs['drone_capabilities']
print("\n=== drone_capabilities (idx: type, cap, rem, speed) ===")
for i, c in enumerate(caps):
    print(f"  drone_{i}: {c.get('drone_type')} cap={c.get('carrying_capacity')} rem={c.get('remaining_capacity')} speed={c.get('speed')}")

tasks = [t for t in obs['unassigned_tasks'] if not str(t['task_id']).startswith('__pad_')]
print("\n=== unassigned_tasks (order) ===")
for t in tasks:
    print(f"  {t['task_id']}: weight={t.get('weight')} src=({t['source'][0]:.0f},{t['source'][1]:.0f}) route_dist={t.get('route_distance')} remaining_time={t.get('remaining_time')}")

# 手动复现 _best_drone_for_task 对每个任务的抉择
print("\n=== manual trace of _on_new_task ===")
sched = ps.PSOScheduler(num_drones=len(env.drones), verbose=False, seed=101)
sched._extract_capacity(obs)
is_free = sched._extract_is_free(obs)
for t in tasks:
    sched.known_task_ids.add(t['task_id'])
    tid = t['task_id']
    tw = float(t.get('weight', 0.0))
    available = [i for i in range(sched.num_drones)
                 if is_free[i] and i not in sched.active_task_ids and len(sched.drone_queues[i]) == 0]
    feasible = [i for i in available if tw <= sched._drone_remaining[i] + 1e-9]
    if feasible:
        best = sched._best_drone_for_task(feasible, t, obs, 0)
        sched.drone_queues[best].append(t)
        print(f"  {tid} w={tw} -> drone_{best} ({caps[best].get('drone_type')}) feasible={feasible}")
    else:
        print(f"  {tid} w={tw} -> BUFFER (no feasible; available={available})")