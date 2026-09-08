import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "simulation"))

from simulation.environment import Environment
from scheduling.ga_scheduler import GAScheduler

env = Environment(str(PROJECT_ROOT / "simulation" / "data" / "map" / "part_of_yangpu.osm"),
                  visualize=False, episode_max_steps=2000)
obs = env.reset(seed=101)
sched = GAScheduler(num_drones=len(env.drones), verbose=False, seed=101)

print(f"num_drones={len(env.drones)}")

for t in range(400):
    free = [bool(f) for f in obs.get('drone_is_free', [])]
    n_free = sum(free)
    n_idle = sum(1 for i in range(sched.num_drones)
                 if free[i] and i not in sched.active_task_ids and len(sched.drone_queues[i]) == 0)
    n_queue_nonempty = sum(1 for i in range(sched.num_drones) if sched.drone_queues[i])

    action = sched.step(obs, current_time=env.current_time)
    n_disp = sum(1 for v in action.values() if v)

    if t % 40 == 0 or t < 6:
        buf_weights = sorted(round(float(tk.get('weight', 0)), 1) for tk in sched.pending_buffer)
        cap_obs = obs.get('drone_capabilities', [])
        idle_info = []
        for i in range(sched.num_drones):
            if free[i] and i not in sched.active_task_ids and len(sched.drone_queues[i]) == 0:
                c = cap_obs[i] if i < len(cap_obs) else {}
                idle_info.append(f"{c.get('drone_type','?')}(rem={c.get('remaining_capacity','?')})")
        print(f"t={t:4d} free={n_free:2d} idle={n_idle:2d} buffer={len(sched.pending_buffer):2d} "
              f"buf_w={buf_weights} | idle_types={idle_info} | "
              f"imm={sched.stats['immediate_assign']:3d} buf={sched.stats['buffered']:3d} "
              f"drain={sched.stats['buffer_drain']:3d} fT={sched.stats['flush_timeout']:2d} "
              f"fE={sched.stats['flush_emergency']:2d} fS={sched.stats['flush_size']:2d}")

    obs, _, done, _ = env.step(action)
    if done:
        break