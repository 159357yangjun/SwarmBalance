# -*- coding: utf-8 -*-
"""P2.2 strict flight feasibility contract, real Drone.update/Environment.step.

This test MUST be RED on P2.1 SHA 806d076: energy depletion was a debit
warning but did not prevent impossible movement. No skip/xfail is allowed.
"""
from __future__ import annotations
import math
import os
from unittest.mock import patch
from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit


class EnergyGateContract(LoadEnergyLedgerAudit):
    def scene(self, *, battery, route, load=0, onboard=0):
        d=self.drone(capacity=10.0,load=load,battery=5.0,base=0.06,penalty=0.33)
        d.onboard_load_kg=onboard
        d.current_battery=battery
        d.scheduled_position=list(route)
        env=self.small_environment(d)
        return d,env

    def test_P2_2_insufficient_first_leg_is_blocked_before_motion_and_debit(self):
        d,env=self.scene(battery=0.2,route=[(20.0,0.0,"source"),(40.0,0.0,"dest")])
        route=list(d.scheduled_position)
        env.step({})
        self.assertEqual((d.x,d.y),(0.0,0.0),"[P2_2_NO_ENERGY_NO_MOTION]")
        self.assertEqual(d.scheduled_position,route,"[P2_2_ROUTE_PRESERVED]")
        self.assertEqual(d.consumed_waypoints_this_step,[],"[P2_2_NO_FAKE_SERVICE]")
        self.assertAlmostEqual(d.current_battery,0.2,"[P2_2_NO_PARTIAL_DEBIT]")
        self.assertAlmostEqual(d.last_energy_required_wh,1.2)
        self.assertAlmostEqual(d.last_energy_debited_wh,0)
        self.assertAlmostEqual(d.last_energy_shortfall_wh,1.2)
        self.assertTrue(d.energy_insufficient)
        self.assertTrue(d.flight_energy_blocked)
        self.assertFalse(d.is_free)
        self.assertAlmostEqual(env.total_energy_consumed,0)
        self.assertAlmostEqual(env.total_flight_distance,0)

    def test_P2_2_empty_battery_does_not_advance_second_leg(self):
        d,env=self.scene(battery=0,route=[(20.0,0.0,"waypoint"),(40.0,0.0,"dest")])
        for _ in range(2):
            env.step({})
            self.assertEqual((d.x,d.y),(0.0,0.0),"[P2_2_ZERO_BATTERY_MOVE]")
            self.assertEqual(len(d.scheduled_position),2)
            self.assertEqual(d.consumed_waypoints_this_step,[])
            self.assertAlmostEqual(d.current_battery,0)
        self.assertAlmostEqual(env.total_flight_distance,0)
        self.assertFalse(d.is_free)

    def test_P2_2_partial_step_is_blocked_before_motion(self):
        d,env=self.scene(battery=0.1,route=[(100.0,0.0,"dest")],load=0)
        env.step({})
        self.assertEqual((d.x,d.y),(0,0))
        self.assertAlmostEqual(d.current_battery,0.1)
        self.assertEqual(d.scheduled_position,[(100.0,0.0,"dest")])
        self.assertAlmostEqual(d.last_energy_required_wh,1.2)

    def test_P2_2_onboard_experimental_mass_and_wind_neutral_quote(self):
        with patch.dict(os.environ,{"SWARM_BALANCE_ENERGY_ACCOUNTING":"onboard"}):
            d,env=self.scene(battery=0.2,route=[(20.0,0.0,"dest")],load=5,onboard=5)
            env.step({})
            self.assertEqual((d.x,d.y),(0.0,0.0),"[P2_2_ONBOARD_BLOCK]")
            self.assertAlmostEqual(d.last_energy_required_wh,1.2*(1+0.5*0.33))
            self.assertAlmostEqual(d.current_battery,0.2)
            self.assertAlmostEqual(env.total_loaded_distance+env.total_empty_distance,0)

    def test_P2_2_exact_budget_allows_actual_service(self):
        d,env=self.scene(battery=1.2,route=[(20.0,0.0,"dest")])
        env.step({})
        self.assertEqual((d.x,d.y),(20.0,0.0))
        self.assertEqual(d.scheduled_position,[])
        self.assertAlmostEqual(d.current_battery,0)
        self.assertAlmostEqual(d.last_energy_shortfall_wh,0)
        self.assertAlmostEqual(env.total_flight_distance,20.0)

    def test_P2_2_energy_replenishment_resumes_same_route(self):
        d,env=self.scene(battery=0.2,route=[(20.0,0.0,"waypoint"),(40.0,0.0,"dest")])
        env.step({})
        self.assertEqual((d.x,d.y),(0.0,0.0))
        self.assertTrue(d.flight_energy_blocked)
        d.current_battery=3.0  # represents separately authorized replenishment
        env.step({})
        self.assertEqual((d.x,d.y),(20.0,0.0),"[P2_2_RESUME]")
        self.assertFalse(d.flight_energy_blocked)
        self.assertAlmostEqual(d.current_battery,1.8)
        self.assertEqual(d.scheduled_position,[(40.0,0.0,"dest")])
        env.step({})
        self.assertEqual((d.x,d.y),(40.0,0.0))
        self.assertAlmostEqual(d.current_battery,0.6)
        self.assertEqual(d.scheduled_position,[])
