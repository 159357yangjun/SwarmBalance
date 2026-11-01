"""One episode runner and result-path policy used by all command-line adapters."""
from swarmbalance.paths import PROJECT_ROOT, DEFAULT_MAP, resolve_resource
from swarmbalance.simulation.environment import Environment
from swarmbalance.scheduling.registry import create_scheduler

POLICY_MAP = {
    "greedy": ("greedy", "frontend_greedy_metrics.csv"),
    "pso": ("pso", "backend_si_metrics.csv"),
    "ga": ("ga", "backend_ga_metrics.csv"),
    "ortools": ("ortools", "backend_ortools_metrics.csv"),
}

def _get_metrics_output(policy, record_into_evidence=False):
    """解析默认输出路径。

    默认写到 ``results/adhoc/``（已在 .gitignore 里）。显式加
    ``--record-into-evidence`` 才写到 Web 对比页的数据目录；当前仓库
    没有附带历史对比 CSV，输出位置不代表结果已通过可比性验证。

    ``record_into_evidence=True`` 时优先读 simulation.json 的 metrics 配置
    （compare_dir 与 ``<policy>_file`` 可覆盖），否则用默认文件名。
    """
    _, default_filename = POLICY_MAP[policy]
    if not record_into_evidence:
        return PROJECT_ROOT / "results" / "adhoc" / default_filename

    cfg_path = PROJECT_ROOT / "config" / "simulation.json"
    compare_dir = PROJECT_ROOT / "results" / "compare"
    filename = default_filename

    if cfg_path.exists():
        import json
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        metrics_cfg = cfg.get("metrics", {}) if isinstance(cfg, dict) else {}
        compare_dir = PROJECT_ROOT / metrics_cfg.get("compare_dir", "results/compare")
        # 允许配置覆盖文件名；未配置则保持默认
        override_key = f"{policy}_file"
        filename = metrics_cfg.get(override_key, filename)

    return compare_dir / filename


def _build_scheduler(policy, env, seed):
    return create_scheduler(policy, num_drones=len(env.drones), seed=seed)


def run_one_episode(osm_path, episode_steps, policy, seed, *, include_scheduler_stats=False):
    env = Environment(str(resolve_resource(osm_path)), episode_max_steps=episode_steps)
    observation = env.reset(seed=seed)
    scheduler = _build_scheduler(policy, env, seed)
    done = False
    while not done:
        action = scheduler.act(observation, current_time=env.current_time)
        observation, _, done, _ = env.step(action)
    stats = env.get_statistics()
    stats["episode_step"] = int(env.current_time)
    if include_scheduler_stats and policy != "greedy":
        stats["_scheduler_stats"] = scheduler.get_stats()
    return stats
