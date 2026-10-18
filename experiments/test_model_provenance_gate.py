# -*- coding: utf-8 -*-
"""Read-only audit gates for experiment provenance and paired E0/E1 plans.

These tests intentionally DO NOT run new physics simulations, alter E0/E1
results, or claim measured airframe-energy calibration.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.runner import build_plan, load_preset
from experiments.reproducibility import write_manifest

ROOT = Path(__file__).resolve().parents[1]

CUSTODY_GATES = (
    "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE",
    "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF",
    "SWARM_BALANCE_B5C_MIXED_CHAIN_RELEASE",
    "SWARM_BALANCE_B5F_QUEUE_RECONCILIATION",
    "SWARM_BALANCE_B5G_SERIALIZED_RECONCILIATION",
)
RECOVERY_GATES = (
    "SWARM_BALANCE_INFLIGHT_WIND_REQUOTE",
    "SWARM_BALANCE_HELD_ROUTE_REQUOTE",
    "SWARM_BALANCE_AUTO_PLANNED_STATION",
    "SWARM_BALANCE_CHARGE_TARGET_IDENTITY",
    "SWARM_BALANCE_PLANNED_STATION_ROUTE",
    "SWARM_BALANCE_STATION_ENERGY_GATE",
)


class ResearchProvenanceGate(unittest.TestCase):
    def _manifest(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_manifest(
                Path(td), ROOT, None,
                ROOT / "config" / "simulation.json",
                ROOT / "config" / "algorithms.yaml",
                ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm",
                1, ["greedy"], "audit_only",
            )
            return json.loads(path.read_text(encoding="utf-8"))

    def test_AUD01_active_experimental_flags_are_in_provenance(self):
        flags = {k: "0" for k in CUSTODY_GATES + RECOVERY_GATES}
        flags.update({
            "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
            "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
            "SWARM_BALANCE_B5F_QUEUE_RECONCILIATION": "1",
            "SWARM_BALANCE_B5G_SERIALIZED_RECONCILIATION": "1",
            "SWARM_BALANCE_INFLIGHT_WIND_REQUOTE": "1",
        })
        with patch.dict(os.environ, flags):
            manifest = self._manifest()
        got = manifest["environment_flags"]
        for name, value in flags.items():
            self.assertEqual(got.get(name), value, "[AUD_FLAG_UNTRACEABLE] " + name)
        self.assertIn("SWARM_BALANCE_SIM_CONFIG", got)

    def test_AUD02_defaults_are_explicit_and_do_not_claim_optin(self):
        with patch.dict(os.environ, {k: "0" for k in CUSTODY_GATES + RECOVERY_GATES}):
            manifest = self._manifest()
        flags = manifest["environment_flags"]
        for name in CUSTODY_GATES + RECOVERY_GATES:
            self.assertEqual(flags.get(name), "0", "[AUD_DEFAULT_GATE_UNTRACEABLE] " + name)
        self.assertFalse(any(flags.get(k) == "1" for k in CUSTODY_GATES))

    def test_AUD03_enabled_sqlite_custody_sources_are_hashed(self):
        with patch.dict(os.environ, {
            "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
            "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
            "SWARM_BALANCE_B5F_QUEUE_RECONCILIATION": "1",
            "SWARM_BALANCE_B5G_SERIALIZED_RECONCILIATION": "1",
        }):
            manifest = self._manifest()
        hashes = manifest["core_source_sha256"]
        for relative in (
            "console/custody_journal.py",
            "console/custody_transaction.py",
            "console/custody_queue_bridge.py",
        ):
            self.assertEqual(len(hashes.get(relative, "")), 64,
                             "[AUD_CUSTODY_SOURCE_UNTRACEABLE] " + relative)

    def test_AUD04_e0_e1_calm_identical_fixture_and_paired_seeds(self):
        e0 = build_plan(load_preset("e0_baseline"))
        e1 = build_plan(load_preset("e1_wind_clash"))
        self.assertEqual(len(e0), 6, "[AUD_E0_PLAN_DRIFT]")
        self.assertEqual(len(e1), 18, "[AUD_E1_PLAN_DRIFT]")
        baseline = {(r.value, r.repeat): r for r in e0}
        self.assertEqual({r.value for r in e0}, {"C1", "C2"})
        for experiment in e1:
            parts = experiment.value.split("×")
            self.assertEqual(len(parts), 2)
            fixture, wind = parts
            self.assertIn(wind, {"calm", "east6", "west6"})
            reference = baseline[(fixture, experiment.repeat)]
            self.assertEqual(reference.seed, experiment.seed, "[AUD_SEED_UNPAIRED]")
            for key in ("task_generation", "environment", "heterogeneous"):
                self.assertEqual(reference.patch.get(key), experiment.patch.get(key),
                                 "[AUD_SCENARIO_DRIFT] " + key)
            if wind == "calm":
                self.assertEqual(experiment.patch["wind"], {"u_ms": 0.0, "v_ms": 0.0})
        self.assertEqual({r.seed for r in e0}, {r.seed for r in e1})

    def test_AUD05_read_only_does_not_mutate_frozen_preset_files(self):
        paths = [ROOT / "experiments" / "presets" / s
                 for s in ("e0_baseline.yaml", "e1_wind_clash.yaml")]
        original = [p.read_bytes() for p in paths]
        with patch.dict(os.environ, {k: "0" for k in CUSTODY_GATES + RECOVERY_GATES}):
            self._manifest()
        build_plan(load_preset("e0_baseline"))
        build_plan(load_preset("e1_wind_clash"))
        self.assertEqual([p.read_bytes() for p in paths], original,
                         "[AUD_FROZEN_INPUT_MUTATED]")


if __name__ == "__main__":
    unittest.main()
