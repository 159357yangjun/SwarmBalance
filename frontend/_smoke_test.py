"""临时冒烟测试：验证调度接口抽象 + 数据源适配层。跑完即删。"""
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent
PROJECT = FRONTEND.parent
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(FRONTEND))

from scheduling_interface import Scheduler, SCHEMA_VERSION, Action
from data_source import (RandomDataSource, CSVDataSource, GeoJSONDataSource,
                         build_data_source)
from greedy.scheduler import GreedyScheduler, greedy_action_from_observation
from backend_si.pso_scheduler import PSOScheduler
from backend_si.ga_scheduler import GAScheduler

print("SCHEMA_VERSION =", SCHEMA_VERSION)

# 1) 三算法都实现统一接口 act()
assert callable(GreedyScheduler.act), "greedy.act missing"
assert callable(PSOScheduler.act), "pso.act missing"
assert callable(GAScheduler.act), "ga.act missing"
print("[ok] Greedy/PSO/GA 均暴露统一 act(observation, current_time) 入口")

# 2) 数据源解析
random_ds = RandomDataSource()
print("[random] drones=%d nests=%d" % (len(random_ds.load_drones()), len(random_ds.load_nests())))

csv_ds = CSVDataSource()
print("[csv] drones=%d nests=%d tasks=%d" % (
    len(csv_ds.load_drones()), len(csv_ds.load_nests()), len(csv_ds.load_tasks())))
assert len(csv_ds.load_drones()) == 5, "csv drones parse failed"
assert len(csv_ds.load_nests()) == 3, "csv nests parse failed"
assert len(csv_ds.load_tasks()) == 4, "csv tasks parse failed"

geo_ds = GeoJSONDataSource()
print("[geojson] drones=%d nests=%d tasks=%d" % (
    len(geo_ds.load_drones()), len(geo_ds.load_nests()), len(geo_ds.load_tasks())))
assert len(geo_ds.load_drones()) == 3, "geojson drones parse failed"
assert len(geo_ds.load_nests()) == 2, "geojson nests parse failed"
assert len(geo_ds.load_tasks()) == 2, "geojson tasks parse failed"

# 3) 工厂默认回落随机源
assert build_data_source().source_type == "random"
print("[ok] 数据源适配层解析正确")

# 4) 回归：随机源 + 贪心 跑一小段（headless）
from environment import Environment

env = Environment(str(FRONTEND / "data" / "map" / "part_of_yangpu.osm"),
                  visualize=False, episode_max_steps=40)
obs = env.reset(seed=100)
done = False
steps = 0
while not done and steps < 40:
    action = greedy_action_from_observation(obs)
    obs, _, done, _ = env.step(action)
    steps += 1
s = env.get_statistics()
print("[greedy-random] steps=%d completed=%s generated=%s" % (
    steps, s["total_completed"], s["total_generated"]))

# 5) 回归：CSV 静态源 + 贪心，验证静态任务能跑通并收尾
env2 = Environment(str(FRONTEND / "data" / "map" / "part_of_yangpu.osm"),
                   visualize=False, episode_max_steps=400, data_source=CSVDataSource())
obs = env2.reset(seed=100)
done = False
steps = 0
while not done and steps < 400:
    action = greedy_action_from_observation(obs)
    obs, _, done, _ = env2.step(action)
    steps += 1
s2 = env2.get_statistics()
print("[greedy-csv] steps=%d completed=%s/%s done=%s" % (
    steps, s2["total_completed"], s2["total_generated"], done))
assert s2["total_generated"] == 4, "csv static task count mismatch"

print("ALL SMOKE TESTS PASSED")