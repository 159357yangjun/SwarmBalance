# -*- coding: utf-8 -*-
"""B3c RED-first: real arrival station identity, berth, closure fail-closed.

No simulated physical landing assertion. All new behavior is explicitly
opt-in, with default-off comparison. Existing Environment.step/Drone.update
execute every meaningful movement; berth management is real, not mocked.
"""
from __future__ import annotations

import os
from types import MethodType
from unittest.mock import patch

from scripts.test_p2_4b_b3b_planned_charge_route import PlannedManualChargeRoute


_OPTS = {"SWARM_BALANCE_PLANNED_STATION_ROUTE": "1",
         "SWARM_BALANCE_CHARGE_TARGET_IDENTITY": "1"}


class TargetStationIdentityGate(PlannedManualChargeRoute):
    def _two_stations(self, *, same_coords=True, full_berth=False):
        d, env, b = self._setup_route(obstacle=False)
        a = self.envmod.ChargingStation("A", 100.0 if same_coords else 20.0,
                                       0.0, berths=1)
        b = self.envmod.ChargingStation("B", 100.0, 0.0,
                                       swap_time_seconds=3, berths=1)
        if full_berth:
            b.occupied = 1
        # A comes first deliberately; nearest-by-distance ties must not
        # silently change the requested station to A.
        env.charging_stations = [a, b]
        d.known_stations = [a, b]
        env._nest_waiting = {}
        env._berth_wait_time_sum = 0.0
        env._berth_wait_count = 0
        env._berth_wait_max = 0.0
        env._berth_wait_urgency_sum = 0.0
        env._berth_wait_task_urgency_sum = 0.0
        env._berth_occupied_sum = 0
        env.total_swap_sessions = 0
        env.arbitration_policy = "fifo"
        env._manage_berths = MethodType(self.Environment._manage_berths, env)
        return d, env, a, b

    @patch.dict(os.environ, _OPTS)
    def test_B3c_01_colocated_requested_B_keeps_B_identity_at_real_arrival(self):
        d, env, a, b = self._two_stations(same_coords=True, full_berth=True)
        route = list(d.scheduled_position)
        env.request_drone_charge(0, station_id=b.station_id)
        self.assertEqual(str(d.charge_target_station_id), "B",
                         "[B3C_MISSING_EXPLICIT_TARGET_ID]")
        for _ in range(12):
            if d.awaiting_berth:
                break
            env.step({})
        self.assertTrue(d.awaiting_berth, "[B3C_NO_REAL_ARRIVAL]")
        self.assertEqual(d.get_position(), b.get_position())
        self.assertEqual(str(d.berth_station_id), "B",
                         "[B3C_NEAREST_TIE_WRONG_STATION]")
        self.assertFalse(d.is_charging)
        self.assertEqual(a.occupied, 0)
        self.assertEqual(b.occupied, 1)
        self.assertEqual(env._nest_waiting.get(b.station_id), [0])
        self.assertEqual(d._suspended_route, route)

    @patch.dict(os.environ, _OPTS)
    def test_B3c_02_target_queue_grants_B_only_after_real_berth_release(self):
        d, env, a, b = self._two_stations(same_coords=True, full_berth=True)
        env.request_drone_charge(0, station_id=b.station_id)
        for _ in range(12):
            if d.awaiting_berth:
                break
            env.step({})
        self.assertTrue(d.awaiting_berth)
        self.assertEqual(str(d.berth_station_id), "B")
        self.assertEqual(env.total_swap_sessions, 0)
        b.vacate()  # explicit external berth release; no energy credit
        env.step({})
        self.assertTrue(d.is_charging)
        self.assertEqual(str(d.charging_station_id), "B")
        self.assertEqual(b.occupied, 1)
        self.assertEqual(a.occupied, 0)
        self.assertEqual(env.total_swap_sessions, 1)
        for _ in range(5):
            env.step({})
        self.assertEqual(b.occupied, 0)
        self.assertEqual(env.total_swap_sessions, 1)
        self.assertEqual(d._suspended_route, [])
        self.assertFalse(d.is_charging)

    @patch.dict(os.environ, _OPTS)
    def test_B3c_03_closure_midflight_does_not_redirect_without_quote(self):
        d, env, a, b = self._two_stations(same_coords=False)
        original = list(d.scheduled_position)
        env.request_drone_charge(0, station_id=b.station_id)
        env.step({})
        self.assertGreater(d.x, 0.0)
        remaining = list(d.scheduled_position)
        before = (d.get_position(), d.current_battery, env.total_energy_consumed)
        result = env.set_station_closed(b.station_id, True)
        self.assertTrue(result["changed"])
        self.assertEqual(d.scheduled_position, remaining,
                         "[B3C_CLOSED_NEST_UNQUOTED_DIRECT_REROUTE]")
        self.assertEqual(str(d.charge_target_station_id), "B")
        self.assertEqual(d.charge_target_hold_reason, "target_station_closed")
        env.step({})
        self.assertEqual((d.get_position(), d.current_battery,
                          env.total_energy_consumed), before,
                         "[B3C_CLOSED_NEST_MOVEMENT_OR_ENERGY]")
        self.assertFalse(d.awaiting_berth)
        self.assertFalse(d.is_charging)
        self.assertEqual(d._suspended_route, original)
        self.assertEqual(env.total_swap_sessions, 0)

    @patch.dict(os.environ, {"SWARM_BALANCE_PLANNED_STATION_ROUTE": "1",
                              "SWARM_BALANCE_CHARGE_TARGET_IDENTITY": "0"})
    def test_B3c_04_default_off_preserves_legacy_tied_nearest(self):
        d, env, a, b = self._two_stations(same_coords=True, full_berth=True)
        env.request_drone_charge(0, station_id=b.station_id)
        for _ in range(12):
            if d.awaiting_berth or d.is_charging:
                break
            env.step({})
        self.assertTrue(d.is_charging, "[B3C_LEGACY_CONTROL_CHANGED]")
        self.assertEqual(str(d.charging_station_id), "A")
        self.assertEqual(a.occupied, 1)
        self.assertEqual(b.occupied, 1)

    @patch.dict(os.environ, _OPTS)
    def test_B3c_05_forged_waiting_far_from_nest_never_gets_berth_or_energy(self):
        d, env, a, b = self._two_stations(same_coords=False)
        d.charge_target_station_id = "B"
        d.awaiting_berth = True  # corrupt/unwitnessed state: at (0,0)
        d.berth_station_id = "B"
        d._manual_charge_requested = True
        before = d.current_battery
        env._manage_berths()  # actual berth allocator, not a stub
        self.assertEqual(d.get_position(), (0.0, 0.0))
        self.assertFalse(d.is_charging, "[B3C_FAKE_ARRIVAL_GRANTED_BERTH]")
        self.assertEqual(b.occupied, 0)
        self.assertEqual(env.total_swap_sessions, 0)
        self.assertEqual(d.current_battery, before)

    @patch.dict(os.environ, _OPTS)
    def test_B3c_06_forged_wrong_target_queue_cannot_swap_at_A(self):
        d, env, a, b = self._two_stations(same_coords=True)
        d.x, d.y = b.get_position()
        d.charge_target_station_id = "B"
        d.awaiting_berth = True  # wrong station ID despite identical coordinates
        d.berth_station_id = "A"
        d._manual_charge_requested = True
        env._manage_berths()
        self.assertFalse(d.is_charging, "[B3C_FAKE_TARGET_ID_GRANTED_BERTH]")
        self.assertEqual((a.occupied, b.occupied), (0, 0))
        self.assertEqual(env.total_swap_sessions, 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
