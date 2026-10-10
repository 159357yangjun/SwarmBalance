# -*- coding: utf-8 -*-
"""P2.1 diagnostic read-only audit of real Drone.update / Environment.step.

This is characterization, NOT an authorization to change flight policies.
An energy shortfall must be reported separately from the physically impossible
leg; expected violation is recorded explicitly and must not be called a PASS.
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit


class BatteryFeasibilityAudit(LoadEnergyLedgerAudit):
    def test_exact_energy_budget_reaches_destination_without_shortfall(self):
        d=self.drone(load=0.0,battery=5.0,base=0.06)
        d.current_battery=1.2
        d.scheduled_position=[(20.0,0.0,"waypoint")]
        env=self.small_environment(d)
        env.step({})
        self.assertAlmostEqual(d.x,20.0)
        self.assertAlmostEqual(d.current_battery,0.0)
        self.assertAlmostEqual(d.last_energy_required_wh,1.2)
        self.assertAlmostEqual(d.last_energy_debited_wh,1.2)
        self.assertAlmostEqual(d.last_energy_shortfall_wh,0.0)
        print("[P2_1_CONTROL] exact_budget distance=20 Wh=1.2 shortfall=0")

    def test_P2_1_gap_closed_by_P2_2_movement_gate(self):
        """Original failing behavior remains witnessed in P2.1 Actions #38030425133.

        After P2.2, update diagnostic to assert no physical impossible leg.
        Direct consume_battery() ledger semantics remain unchanged.
        """
        d=self.drone(load=0.0,battery=5.0,base=0.06)
        d.current_battery=0.2
        d.scheduled_position=[(20.0,0.0,"waypoint"),(40.0,0.0,"waypoint")]
        env=self.small_environment(d)
        for step in (1,2):
            env.step({})
            self.assertEqual((d.x,d.y),(0,0),"[P2_2_NO_UNPAID_MOVEMENT]")
            self.assertEqual(len(d.scheduled_position),2)
            self.assertAlmostEqual(d.current_battery,0.2)
            self.assertAlmostEqual(d.last_energy_required_wh,1.2)
            self.assertAlmostEqual(d.last_energy_debited_wh,0)
            self.assertAlmostEqual(d.last_energy_shortfall_wh,1.2)
            self.assertTrue(d.flight_energy_blocked)
            print("[P2_1_FIXED] step=%d stationary_with_energy_shortfall"%step)

    def test_out_of_service_freezes_motion_and_energy(self):
        d=self.drone(load=0.0,battery=5.0,base=0.06)
        d.current_battery=0.2
        d.out_of_service=True
        d.scheduled_position=[(20.0,0.0,"waypoint")]
        env=self.small_environment(d)
        env.step({})
        self.assertEqual((d.x,d.y),(0.0,0.0))
        self.assertAlmostEqual(d.current_battery,0.2)
        print("[P2_1_CONTROL] explicit_out_of_service holds position and battery")


if __name__=="__main__":
    unittest.main(verbosity=2)
