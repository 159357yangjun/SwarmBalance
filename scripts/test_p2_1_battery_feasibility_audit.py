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

    def test_true_low_energy_continuation_exposes_physical_contract_gap(self):
        d=self.drone(load=0.0,battery=5.0,base=0.06)
        d.current_battery=0.2
        d.scheduled_position=[(20.0,0.0,"waypoint"),(40.0,0.0,"waypoint")]
        env=self.small_environment(d)
        origin=(d.x,d.y)
        env.step({})
        self.assertAlmostEqual(d.current_battery,0.0)
        self.assertAlmostEqual(d.last_energy_required_wh,1.2)
        self.assertAlmostEqual(d.last_energy_debited_wh,0.2)
        self.assertAlmostEqual(d.last_energy_shortfall_wh,1.0)
        self.assertTrue(d.energy_insufficient)
        moved=math.dist(origin,(d.x,d.y))
        if moved>0:
            print("[P2_1_PHYSICAL_GAP] leg_with_shortfall moved_m=%.3f required_wh=%.3f debited_wh=%.3f shortfall_wh=%.3f"%(moved,d.last_energy_required_wh,d.last_energy_debited_wh,d.last_energy_shortfall_wh),flush=True)
        else:
            print("[P2_1_PHYSICAL_BARRIER] blocked_motion_on_shortfall")
        # Hard invariant: insufficient battery never drops below zero, gap is explicit.
        self.assertGreaterEqual(d.current_battery,0.0)
        self.assertAlmostEqual(d.last_energy_required_wh,d.last_energy_debited_wh+d.last_energy_shortfall_wh)
        # Observe second real update: does the vehicle continue for zero Wh?
        before=(d.x,d.y)
        env.step({})
        moved2=math.dist(before,(d.x,d.y))
        if moved2>0 and d.last_energy_debited_wh==0:
            print("[P2_1_PHYSICAL_GAP] second_leg_zero_battery_movement moved_m=%.3f"%moved2,flush=True)
        else:
            print("[P2_1_SECOND_LEG] distance_m=%.3f debit_wh=%.3f"%(moved2,d.last_energy_debited_wh))
        self.assertGreaterEqual(d.current_battery,0.0)

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
