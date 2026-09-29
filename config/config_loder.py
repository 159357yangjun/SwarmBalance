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
    """配置来源指纹：(解析后的绝对路径, 内容 md5)。

    给需要"文件没变就别重算"的调用方用（例如 SimSession 的环境结构指纹，
    以前每次 /api/snapshot 都要重开文件 + json.load + md5）。
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


_UNSET = object()


def get_episode_max_steps(config_path=None, config=_UNSET):
    """单回合最大步数的**唯一**来源：``config/simulation.json`` 的
    ``environment.episode_max_steps``。

    这里刻意**不提供默认值**。原先有 7 处各自硬编码的 fallback，实测取值互不相同：
    ``frontend/environment.py`` 1200、``console/sim_session.py`` 2000、
    ``frontend/evaluate_metrics.py`` 1200（且完全不读配置）、
    ``run_ga/run_pso/run_ortools/run_greedy`` 各 1200，而配置本身是 3600。
    后果不是文案不准，而是"同一个『默认』能跑出 3 种长度的实验"：
    ``results/compare/`` 里三份手写 CSV 的总步数正是 2000，与结项实验的 3600 上限
    不同口径，横向对比因此不可比。缺配置时必须当场失败，而不是悄悄换一个数跑。

    ``config`` 用哨兵而非 None 判缺省：调用方显式传 None（配置没读到/为空）也要抛错，
    不能退回读文件 —— 否则"缺配置即失败"这条保证会被一个 None 参数绕过去。
    """
    cfg = get_shared_config(config_path) if config is _UNSET else config
    env_cfg = (cfg or {}).get("environment") or {}
    if "episode_max_steps" not in env_cfg:
        raise RuntimeError(
            "配置缺少 environment.episode_max_steps，拒绝使用任何隐式默认值。\n"
            "  配置来源：%s\n"
            "  本项是单回合步数的唯一真源；历史上这里散落过 1200 / 2000 两套 fallback，"
            "导致同一个『默认』跑出不同长度的实验。请显式写入该键（当前仓库配置为 3600）。"
            % _resolve(config_path))
    try:
        steps = int(env_cfg["episode_max_steps"])
    except (TypeError, ValueError):
        raise RuntimeError("environment.episode_max_steps 不是整数：%r"
                           % (env_cfg["episode_max_steps"],))
    if steps <= 0:
        raise RuntimeError("environment.episode_max_steps 必须为正整数，当前 %d" % steps)
    return steps


def get_shared_config(config_path=None):
    """从 simulation.json 读取配置并返回。

    正常运行时读取项目内 ``config/simulation.json``。一键实验编排器会为每次
    实验生成隔离的临时配置，并通过 ``SWARM_BALANCE_SIM_CONFIG`` 指向它；这样
    批量实验不会改写用户正在调试/演示的主配置。显式传入 ``config_path`` 的优先级
    最高。
    """
    with open(_resolve(config_path), "r", encoding="utf-8") as f:
        return json.load(f)
