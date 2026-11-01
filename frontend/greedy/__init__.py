"""Compatibility package for the canonical Greedy strategy."""
import sys as _sys
from pathlib import Path as _Path

_root = str(_Path(__file__).resolve().parents[2])
if _root not in _sys.path:
    _sys.path.insert(0, _root)

from swarmbalance.scheduling.greedy import GreedyScheduler, greedy_action_from_observation

__all__ = ["GreedyScheduler", "greedy_action_from_observation"]
