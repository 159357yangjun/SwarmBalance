# -*- coding: utf-8 -*-
"""Focused R1 provenance gate. It does not claim flight-energy calibration."""
from __future__ import annotations
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from experiments.reproducibility import write_manifest

ROOT = Path(__file__).resolve().parents[1]


class EnergyAccountingManifestTests(unittest.TestCase):
    def test_requested_and_effective_policy_are_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            for requested, expected, fallback in (
                (None, "assigned", False),
                ("assigned", "assigned", False),
                ("onboard", "onboard", False),
                ("unsupported", "assigned", True),
            ):
                with self.subTest(requested=requested):
                    env = os.environ.copy()
                    env.pop("SWARM_BALANCE_ENERGY_ACCOUNTING", None)
                    if requested is not None:
                        env["SWARM_BALANCE_ENERGY_ACCOUNTING"] = requested
                    with patch.dict(os.environ, env, clear=True):
                        path = write_manifest(
                            Path(temp), ROOT, None,
                            ROOT / "config/simulation.json",
                            ROOT / "backend_si/config.yaml",
                            ROOT / "frontend/data/map/part_of_yangpu.osm",
                            1, ["greedy"], "research_r1_provenance",
                        )
                        d = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(
                        d["energy_accounting_policy"],
                        {
                            "requested": requested,
                            "effective": expected,
                            "fallback_to_assigned": fallback,
                        },
                    )


if __name__ == "__main__":
    unittest.main()
