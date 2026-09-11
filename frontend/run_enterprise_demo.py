"""端到端演示：启动 mock 企业网关 -> EnterpriseDataSource 接入 -> 打印规格 + 实时轮询。

仅演示数据接入层，不跑完整调度 episode（无需地图文件）。接入真实网关时，
把 base_url / api_token 换成企业地址即可，逻辑完全一致。

用法:
    cd frontend
    python run_enterprise_demo.py
"""
import sys
import time
from pathlib import Path

FRONTEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = FRONTEND_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FRONTEND_ROOT))

from mock_enterprise_api import start_server
from enterprise_data_source import EnterpriseDataSource


def main():
    url = start_server(port=8765)
    print(f"mock 企业网关已启动: {url}\n")

    # ---- 快照接入（live=False）：一次性拉取当前在用订单 ----
    ds = EnterpriseDataSource(base_url=url, coord_system="lonlat")
    print("== 快照接入（live=False）==")
    for d in ds.load_drones():
        pos = tuple(round(c, 1) for c in d.base_position)
        print(f"  无人机 {d.drone_id:4s} 机型={str(d.drone_type):16s} 起降点={pos} 载重={d.carrying_capacity}")
    for n in ds.load_nests():
        pos = tuple(round(c, 1) for c in n.position)
        print(f"  机巢   {n.nest_id:4s} 位置={pos} 换电={n.swap_time_seconds}s")
    for t in ds.load_tasks():
        print(f"  订单   {t.task_id:6s} 重量={t.weight:5.1f}kg 类别={t.category:6s} 优先={t.priority} 截止={t.deadline}")

    # ---- 实时接入（live=True）：每个仿真步轮询、按 order_id 去重 ----
    print("\n== 实时接入（live=True）==")
    live = EnterpriseDataSource(base_url=url, coord_system="lonlat", live=True)
    src = live.build_task_source()
    t0 = src.generate_initial_tasks(0.0)
    print(f"  初始订单 {len(t0)} 条: {[t.task_id for t in t0]}")
    print("  等待 2.5s 让第二波订单到达...")
    time.sleep(2.5)
    t1 = src.step(1.0)
    print(f"  新到订单 {len(t1)} 条: {[t.task_id for t in t1]}")
    t2 = src.step(2.0)
    print(f"  再次轮询新到订单 {len(t2)} 条（应为 0，去重有效）")


if __name__ == "__main__":
    main()