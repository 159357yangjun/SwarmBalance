"""Thin adapter for the original ga evaluation entrypoint."""
from swarmbalance.application.evaluation import run_one_episode as _run_one_episode, POLICY_MAP
from swarmbalance.cli.algorithm import main as _main
from swarmbalance.paths import RESULTS_DIR
from swarmbalance.infrastructure.config.loader import get_episode_max_steps as _resolve_episode_steps

ALGORITHM_KEY = "ga"
CSV_OUTPUT = RESULTS_DIR / "compare" / POLICY_MAP[ALGORITHM_KEY][1]


def run_one_episode(osm_path, episode_steps, seed=None):
    return _run_one_episode(osm_path, episode_steps, ALGORITHM_KEY, seed, include_scheduler_stats=True)


def main(argv=None):
    return _main(ALGORITHM_KEY, argv)
