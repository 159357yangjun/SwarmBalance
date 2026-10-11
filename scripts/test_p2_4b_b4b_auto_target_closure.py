# -*- coding: utf-8 -*-
"""B4b RED: actual automatic nest identity and midflight closure, experimental only."""
from __future__ import annotations

import os
from unittest.mock import patch
from scripts.test_p2_4b_b3c_target_station import TargetStationIdentityGate

FLAGS={"SWARM_BALANCE_AUTO_PLANNED_STATION":"1",
       "SWARM_BALANCE_CHARGE_TARGET_IDENTITY":"1",
       "SWARM_BALANCE_STATION_ENERGY_GATE":"0"}

class AutoTargetAndClosure(TargetStationIdentityGate):
    def _setup_auto(self, colocated=True):
        d,env,a,b=self._two_stations(same_coords=colocated,full_berth=False)
        # Put the chosen target B first only in energy priority; A still wins
        # the geometric nearest tie when both stations are colocated.
        a.closed = False
        d.current_battery=12.0
        self.assertTrue(d.is_low_battery())
        d._manual_charge_requested=False
        return d,env,a,b

    @patch.dict(os.environ,FLAGS)
    def test_B4b_auto_target_id_matches_actual_nest_and_berth_on_colocated_sites(self):
        d,env,a,b=self._setup_auto(colocated=True)
        # Co-located station A cannot be silently substituted for explicitly
        # chosen B by nearest-geometry arrival logic.
        a.closed=True
        env.step({})
        self.assertEqual(str(d.charge_target_station_id),"B")
        a.closed=False
        for _ in range(15):
            if d.awaiting_berth or d.is_charging: break
            env.step({})
        self.assertEqual(str(d.berth_station_id or d.charging_station_id),"B",
                         "[B4B_AUTO_TARGET_IDENTITY_MISMATCH]")
        self.assertEqual(a.occupied,0)

    @patch.dict(os.environ,FLAGS)
    def test_B4b_auto_target_closed_midflight_must_hold_without_free_reroute(self):
        d,env,a,b=self._setup_auto(colocated=False)
        # A close station is closed at dispatch, B is chosen on planned Wh.
        a.closed=True
        route=list(d.scheduled_position)
        env.step({})
        self.assertEqual(str(d.charge_target_station_id),"B")
        env.step({})
        self.assertNotEqual(d.get_position(),(0.,0.))
        remaining=list(d.scheduled_position)
        before=(d.get_position(),d.current_battery,env.total_energy_consumed)
        a.closed=False
        env.set_station_closed("B",True)
        self.assertEqual(d.scheduled_position,remaining,
                         "[B4B_UNQUOTED_CLOSURE_REROUTE]")
        self.assertEqual(d.charge_target_hold_reason,"target_station_closed")
        env.step({})
        self.assertEqual((d.get_position(),d.current_battery,env.total_energy_consumed),before,
                         "[B4B_CLOSED_TARGET_STILL_FLYING]")
        self.assertEqual(d._suspended_route,route)
        self.assertFalse(d.is_charging)

    @patch.dict(os.environ,{"SWARM_BALANCE_AUTO_PLANNED_STATION":"0",
                            "SWARM_BALANCE_CHARGE_TARGET_IDENTITY":"0"})
    def test_B4b_default_off_legacy_nearest_policy(self):
        d,env,a,b=self._setup_auto(colocated=False)
        old=list(d.scheduled_position)
        env.step({})
        self.assertEqual(d.scheduled_position,[a.get_position()])
        self.assertEqual(d._suspended_route,old)


    @patch.dict(os.environ,FLAGS)
    def test_B4b_forged_auto_arrival_far_from_target_cannot_get_berth(self):
        d,env,a,b=self._setup_auto(colocated=False)
        d.charge_target_station_id="B"
        d._suspended_route=list(d.scheduled_position)
        d.awaiting_berth=True
        d.berth_station_id="B"
        before=d.current_battery
        env._manage_berths()
        self.assertFalse(d.is_charging, "[B4B_AUTO_REMOTE_FREE_SWAP]")
        self.assertEqual((a.occupied,b.occupied),(0,0))
        self.assertEqual(env.total_swap_sessions,0)
        self.assertEqual(d.current_battery,before)

    @patch.dict(os.environ,FLAGS)
    def test_B4b_forged_auto_wrong_station_same_location_cannot_swap(self):
        d,env,a,b=self._setup_auto(colocated=True)
        d.x,d.y=b.get_position()
        d.charge_target_station_id="B"
        d._suspended_route=list(d.scheduled_position)
        d.awaiting_berth=True
        d.berth_station_id="A"
        env._manage_berths()
        self.assertFalse(d.is_charging, "[B4B_AUTO_WRONG_STATION_FREE_SWAP]")
        self.assertEqual((a.occupied,b.occupied),(0,0))
        self.assertEqual(env.total_swap_sessions,0)

    @patch.dict(os.environ,FLAGS)
    def test_B4b_forged_auto_missing_target_id_cannot_swap(self):
        d,env,a,b=self._setup_auto(colocated=False)
        d.x,d.y=b.get_position()
        d.charge_target_station_id=None
        d._suspended_route=list(d.scheduled_position)
        d.awaiting_berth=True
        d.berth_station_id="B"
        env._manage_berths()
        self.assertFalse(d.is_charging, "[B4B_AUTO_MISSING_TARGET_FREE_SWAP]")
        self.assertEqual(b.occupied,0)
        self.assertEqual(env.total_swap_sessions,0)

    @patch.dict(os.environ,FLAGS)
    def test_B4b_target_state_cleared_after_real_swap_completion(self):
        d,env,a,b=self._setup_auto(colocated=True)
        a.closed=True
        env.step({})
        self.assertEqual(str(d.charge_target_station_id),"B")
        a.closed=False
        seen_charging=False
        for _ in range(25):
            env.step({})
            if d.is_charging:
                seen_charging=True
            if seen_charging and not d.is_charging:
                break
        self.assertTrue(seen_charging,"[B4B_SWAP_NOT_OBSERVED]")
        self.assertFalse(d.is_charging,"[B4B_SWAP_NOT_FINISHED]")
        self.assertIsNone(getattr(d,"charge_target_station_id",None),
                          "[B4B_STALE_TARGET_AFTER_SWAP]")
        self.assertIsNone(getattr(d,"charge_target_hold_reason",None),
                          "[B4B_STALE_HOLD_AFTER_SWAP]")
        self.assertEqual(d._manual_charge_requested,False)
        self.assertEqual(d.executing_task_id,"T1")

if __name__=="__main__":
    import unittest
    unittest.main()
