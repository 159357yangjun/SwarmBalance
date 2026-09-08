import json
from pathlib import Path


def get_shared_config(config_path=None):
    """从 simulation.json 读取配置并返回。"""
    if config_path is None:
        config_path = Path(__file__).resolve().with_name("simulation.json")
    else:
        config_path = Path(config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)