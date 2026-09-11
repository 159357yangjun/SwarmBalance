import json
import os
from pathlib import Path


def get_shared_config(config_path=None):
    """从 simulation.json 读取配置并返回。

    正常运行时读取项目内 ``config/simulation.json``。一键实验编排器会为每次
    实验生成隔离的临时配置，并通过 ``SWARM_BALANCE_SIM_CONFIG`` 指向它；这样
    批量实验不会改写用户正在调试/演示的主配置。显式传入 ``config_path`` 的优先级
    最高。
    """
    if config_path is None:
        override = os.environ.get("SWARM_BALANCE_SIM_CONFIG", "").strip()
        config_path = Path(override) if override else Path(__file__).resolve().with_name("simulation.json")
    else:
        config_path = Path(config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)
