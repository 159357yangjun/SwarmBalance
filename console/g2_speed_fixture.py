# -*- coding: utf-8 -*-
"""G2 speed-fallback-only fixture: isolate speed coverage from battery depletion.

P2.2's fail-closed motion gate is NOT disabled.  This artificial battery
budget is used only in disposable speed/optimizer-denominator unit tests,
never in the production configuration or physical-validation experiments.
The 20x choice has an executable, no-block witness: G2 diagnosis
Actions 38036789460.  Future changes must still assert zero blocked steps.
"""
from __future__ import annotations

import math

G2_TEST_BATTERY_MULTIPLIER = 20.0


def isolate_g2_battery_depletion(config):
    """Adjust temporary G2 scenario config in place; keep all other fields."""
    factor = G2_TEST_BATTERY_MULTIPLIER
    profiles = [config["drone"], *config["heterogeneous"]["drone_types"].values()]
    for p in profiles:
        capacity = float(p["battery_capacity"])
        if not math.isfinite(capacity) or capacity <= 0:
            raise ValueError("[G2_BATTERY_FIXTURE_INVALID] battery_capacity=%r" % capacity)
        p["battery_capacity"] = capacity * factor
    return config
