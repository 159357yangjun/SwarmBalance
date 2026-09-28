import hashlib
import json
import os
from pathlib import Path
from typing import Dict


_SOURCE: Dict[str, Path] = {}


def _resolve(config_path=None) -> Path:
    if config_path is not None:
        return Path(config_path)
    # 默认来源要记忆：Path(__file__).resolve() 在 Windows 上实测 0.2ms 一次，
    # 而它会在每次 /api/snapshot 的指纹计算里被触发，直接把缓存的收益吃光。
    override = os.environ.get("SWARM_BALANCE_SIM_CONFIG", "").strip()
    hit = _SOURCE.get(override)
    if hit is None:
        hit = Path(override) if override else Path(__file__).resolve().with_name("simulation.json")
        if len(_SOURCE) > 64:
            _SOURCE.clear()
        _SOURCE[override] = hit
    return hit


_RESOLVED: Dict[str, str] = {}


def _resolved_str(raw: Path) -> str:
    """Path.resolve() 在 Windows 上很贵（实测 0.41ms/次），而配置来源在一次运行里
    基本不变，所以按原始字符串记忆解析结果。"""
    key = str(raw)
    hit = _RESOLVED.get(key)
    if hit is None:
        try:
            hit = str(raw.resolve())
        except OSError:
            hit = key
        if len(_RESOLVED) > 64:
            _RESOLVED.clear()
        _RESOLVED[key] = hit
    return hit


def config_signature(config_path=None):
    """配置来源指纹：(解析后的绝对路径, mtime_ns, size)。

    给需要"文件没变就别重算"的调用方用（例如 SimSession 的环境结构指纹，
    以前每次 /api/snapshot 都要重开文件 + json.load + md5）。用 stat 而不是
    内容哈希，是因为它足够便宜且能捕捉到界外手改；文件一改签名即变，缓存自然失效。
    """
    p = _resolve(config_path)
    try:
        data = p.read_bytes()
    except OSError:
        return (str(p), None)
    # 不能用 (mtime_ns, size)：实测 40 次内容各异的写入只产生 19 个不同的时间戳+长度组合
    # （Windows 文件时间戳约 10ms 一格），把 num_drones 从 10 改成 11 这种等长改动会完全
    # 躲过签名，指纹缓存就会永久 stale。读内容做哈希实测 0.08ms，仍比它守护的
    # open+json.load(0.18ms) 便宜一半以上。
    return (_resolved_str(p), hashlib.md5(data).hexdigest())


def get_shared_config(config_path=None):
    """从 simulation.json 读取配置并返回。

    正常运行时读取项目内 ``config/simulation.json``。一键实验编排器会为每次
    实验生成隔离的临时配置，并通过 ``SWARM_BALANCE_SIM_CONFIG`` 指向它；这样
    批量实验不会改写用户正在调试/演示的主配置。显式传入 ``config_path`` 的优先级
    最高。
    """
    with open(_resolve(config_path), "r", encoding="utf-8") as f:
        return json.load(f)
