"""Seed interface for reproducible episodes.

This module centralizes RNG seeding and exposes a global seed value so other
parts of the frontend (e.g. `environment.py`) can read it.

Seed range: 0 <= seed <= 2**32 - 1. `None` disables deterministic seeding.

Example: apply + read in another module

    from frontend.seed_interface import apply_seed, get_current_seed

    apply_seed(seed_from_backend)
    current = get_current_seed()          # preferred accessor
    current2 = CURRENT_SEED               # also works (global variable)

Notes:
    seeds from backend-wx usually 100 ~ 300
"""

import random
from typing import Optional

import numpy as np

SEED_MIN = 0
SEED_MAX = 2**32 - 1


# Global seed value for the current episode.
# Updated by `apply_seed()`; `None` means deterministic seeding is disabled.
CURRENT_SEED: Optional[int] = None


def normalize_seed(seed):
    """Normalize the seed to the supported range.

    Seed range: 0 <= seed <= 2**32 - 1. None disables deterministic seeding.
    """
    if seed is None:
        return None
    try:
        value = int(seed)
    except Exception:
        return None

    if value < SEED_MIN or value > SEED_MAX:
        value = value % (SEED_MAX + 1)
    return value


def apply_seed(seed):
    """Apply the seed to Python and NumPy RNGs.

    Returns the normalized seed, or None if seeding is disabled.
    """
    global CURRENT_SEED

    value = normalize_seed(seed)
    CURRENT_SEED = value
    if value is None:
        return None

    random.seed(value)
    np.random.seed(value)
    return value


def get_current_seed() -> Optional[int]:
    """Return the last normalized seed applied by `apply_seed()`.

    This is equivalent to reading `CURRENT_SEED` directly.
    """
    return CURRENT_SEED
