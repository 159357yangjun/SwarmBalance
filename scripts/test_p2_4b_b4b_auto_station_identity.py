# -*- coding: utf-8 -*-
"""B4b real automatic charging-station identity RED/GREEN contract.

After automatic planned detour selects station "A" by Wh+stable ID, a second
colocated station "Z" appears first to geometry-only nearest lookups. Test
real Drone.update, Environment.step and actual berth allocator, not mocks.
This isolates state identity and closure, NOT real-world landing security.
"""
from __future__ import annotations

import os
from unittest.mock import patch
from scripts.test_p2_4b_b3c_target_station import TargetStationIdentityGate

OPT = {
    "SWARM_BALANCE_AUTO_PLANNED_STATION": "1",
    "SWARM_BALANCE_CHARGE_TARGET_IDENTITY": "1",
    "SWARM_BALANCE_STATION_ENERGY_GATE": "0",
    "SWARM_BALANCE_PLANNED_STATION_ROUTE": "0",
}

class AutoStationIdentity(TargetStationIdentityGate):
    def _auto_world(self, *, full_a=True, full_b=True):
        d, env, z, a = self._two_stations(same_coords=True)
        # Both 100m from origin, same energy. B4 A* tie breaker prefers
        # station ID "A" over "Z", even though Z comes first in station list.
        z.station_id = "Z"
        a.station_id = "A"
        z.occupied = int(full_a)
        a.occupied = int(full_b)
        env.charging_stations = [z, a]
        d.known_stations = [z, a]
        env._nest_waiting = {z.station_id: [], a.station_id: []}
        d.current_battery = 12.0  # 100m=6Wh + 5Wh reserve fits, <20% low trigger.
        self.assertTrue(d.is_low_battery())
        self.assertFalse(d._manual_charge_requested)
        self.assertEqual(d._suspended_route, [])
        return d, env, z, a

    def _arrive(self, d, env):
        env.step({})  # assign A* route and suspend mission
        for _ in range(25):
            if d.awaiting_berth or d.is_charging:
                break
            env.step({})

    @patch.dict(os.environ, OPT)
    def test_B4b_01_selected_A_is_actual_A_at_colocated_arrival(self):
        d, env, z, a = self._auto_world()
        original = list(d.scheduled_position)
        self._arrive(d, env)
        self.assertEqual(str(d.charge_target_station_id), "A")
        self.assertEqual(d.get_position(), a.get_position())
        self.assertTrue(d.awaiting_berth, "[B4B_NO_ACTUAL_WAITING_ARRIVAL]")
        self.assertEqual(str(d.berth_station_id), "A",
                         "[B4B_AUTO_TARGET_ID_LOST_TO_NEAREST_TIE]")
        self.assertEqual(env._nest_waiting.get("A"), [0])
        self.assertEqual(env._nest_waiting.get("Z"), [])
        self.assertEqual(d._suspended_route, original)
        self.assertFalse(d.is_charging)
        self.assertEqual((z.occupied, a.occupied), (1, 1))

    @patch.dict(os.environ, OPT)
    def test_B4b_02_only_requested_auto_A_gets_next_released_berth(self):
        d, env, z, a = self._auto_world(full_a=False, full_b=True)
        self._arrive(d, env)
        self.assertTrue(d.awaiting_berth,
                        "[B4B_AUTO_RECHARGED_AT_WRONG_OPEN_STATION]")
        self.assertEqual(str(d.berth_station_id), "A")
        self.assertFalse(d.is_charging)
        self.assertEqual(env.total_swap_sessions, 0)
        a.vacate()  # external berth release input: no free swap
        env.step({})
        self.assertTrue(d.is_charging)
        self.assertEqual(str(d.charging_station_id), "A",
                         "[B4B_AUTO_WRONG_BERTH_GRANTED]")
        self.assertEqual((z.occupied, a.occupied), (0, 1))
        self.assertEqual(env.total_swap_sessions, 1)

    @patch.dict(os.environ, OPT)
    def test_B4b_03_auto_forged_remote_waiting_cannot_gain_charge(self):
        d, env, z, a = self._auto_world(full_a=False, full_b=False)
        d.charge_target_station_id = "A"
        d.awaiting_berth = True
        d.berth_station_id = "A"
        d._manual_charge_requested = False  # automatic, not B3c manual
        before = (d.get_position(), d.current_battery)
        env._manage_berths()
        self.assertEqual((d.get_position(), d.current_battery), before)
        self.assertFalse(d.is_charging,
                         "[B4B_FAKE_AUTO_ARRIVAL_GRANTED_BERTH]")
        self.assertEqual(a.occupied, 0)
        self.assertEqual(env.total_swap_sessions, 0)

    @patch.dict(os.environ, OPT)
    def test_B4b_04_auto_forged_wrong_nest_even_if_colocated_rejected(self):
        d, env, z, a = self._auto_world(full_a=False, full_b=False)
        d.x, d.y = a.get_position()
        d.charge_target_station_id = "A"
        d.awaiting_berth = True
        d.berth_station_id = "Z"
        d._manual_charge_requested = False
        env._manage_berths()
        self.assertFalse(d.is_charging,
                         "[B4B_FAKE_AUTO_ID_GRANTED_DIFFERENT_BERTH]")
        self.assertEqual((z.occupied, a.occupied), (0, 0))
        self.assertEqual(env.total_swap_sessions, 0)

    @patch.dict(os.environ, OPT)
    def test_B4b_05_target_closure_midflight_preserves_auto_manifest(self):
        d, env, z, a = self._auto_world(full_a=False, full_b=False)
        original = list(d.scheduled_position)
        env.step({})  # plan
        env.step({})  # real progress
        self.assertGreater(d.x, 0.0)
        before = (d.get_position(), d.current_battery, env.total_energy_consumed)
        remaining = list(d.scheduled_position)
        self.assertEqual(str(d.charge_target_station_id), "A")
        changed = env.set_station_closed("A", True)
        self.assertTrue(changed["changed"])
        self.assertEqual(d.charge_target_hold_reason, "target_station_closed")
        self.assertEqual(d.scheduled_position, remaining)
        env.step({})
        self.assertEqual((d.get_position(), d.current_battery, env.total_energy_consumed),
                         before, "[B4B_AUTO_CLOSED_TARGET_MOVEMENT]")
        self.assertEqual(d._suspended_route, original)
        self.assertFalse(d.is_charging)
        self.assertEqual(env.total_swap_sessions, 0)

    @patch.dict(os.environ, dict(OPT, SWARM_BALANCE_CHARGE_TARGET_IDENTITY="0"))
    def test_B4b_06_identity_optout_preserves_preexisting_nearest_tie(self):
        d, env, z, a = self._auto_world()
        self._arrive(d, env)
        self.assertEqual(str(d.charge_target_station_id), "A")
        self.assertTrue(d.awaiting_berth)
        self.assertEqual(str(d.berth_station_id), "Z",
                         "[B4B_DEFAULT_IDENTITY_OFF_DRIFT]")
        self.assertEqual(env._nest_waiting.get("Z"), [0])


if __name__ == "__main__":
    import unittest
    unittest.main()
