"""企业数据接入的完整集成测试：mock 网关 -> EnterpriseDataSource -> Environment -> greedy。

验证"真实企业订单"从 REST 接口一路进到仿真环境并被调度完成的整条链路。

用法:
    cd frontend
    python test_enterprise_integration.py
"""
import sys
from pathlib import Path

FRONTEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = FRONTEND_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FRONTEND_ROOT))

from mock_enterprise_api import start_server
from enterprise_data_source import EnterpriseDataSource
from environment import Environment
from greedy.scheduler import greedy_action_from_observation


def main():
    start_server(8765)
    ds = EnterpriseDataSource(
        base_url="http://127.0.0.1:8765", coord_system="lonlat", live=False)
    osm = str(PROJECT_ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm")

    env = Environment(osm, visualize=False, episode_max_steps=300, data_source=ds)
    obs = env.reset(seed=0)
    for _ in range(300):
        obs, _, done, _ = env.step(greedy_action_from_observation(obs))
        if done:
            break

    s = env.get_statistics()
    print("\n=== 集成测试结果 ===")
    for k in ("total_completed", "total_generated", "completion_rate",
              "on_time_rate", "timeout_rate", "avg_delay"):
        print(f"  {k} = {s.get(k)}")


if __name__ == "__main__":
    main()