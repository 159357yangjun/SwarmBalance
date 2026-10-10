# -*- coding: utf-8 -*-
"""P2.4a design-only contract validation. Does NOT imply recovery is deployed."""
from __future__ import annotations

import json
import pathlib
import subprocess
import unittest
from collections import deque

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "contracts" / "p2_4a_recovery_state_machine.json"
DOC = ROOT / "docs" / "P2_4A_RECOVERY_STATE_MACHINE.md"
P22 = "97200d2786a5fc775a8e6ea4ca5f95f90b5bcefb"
ALLOWED_CHANGES = {
    "docs/contracts/p2_4a_recovery_state_machine.json",
    "docs/P2_4A_RECOVERY_STATE_MACHINE.md",
    "scripts/p2_4a_state_contract_test.py",
    ".github/workflows/p2-4a-state-contract.yml",
}


def _load():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def _unique(items):
    names = [row["id"] for row in items]
    return len(set(names)) == len(names)


class RecoveryStateContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = _load()

    def test_01_contract_is_explicitly_design_only(self):
        c = self.c
        self.assertEqual(c["status"], "DESIGN_ONLY_NOT_IMPLEMENTED")
        self.assertEqual(c["source"]["p2_2_head"], P22)
        self.assertEqual(c["source"]["p2_2_full_ci"], 38037310389)
        self.assertEqual(c["default_energy_accounting"], "assigned")
        self.assertTrue(all(s["implementation"] == "planned" for s in c["states"]))
        self.assertTrue(all(t["implementation"] == "planned" for t in c["transitions"]))

    def test_02_state_and_transition_identifiers_are_unique(self):
        for category in ("states", "transitions", "guards", "invariants", "scenarios"):
            self.assertTrue(_unique(self.c[category]), "[P24A_DUPLICATE] " + category)
        self.assertGreaterEqual(len(self.c["states"]), 10)
        self.assertGreaterEqual(len(self.c["transitions"]), 15)
        self.assertGreaterEqual(len(self.c["invariants"]), 14)
        self.assertGreaterEqual(len(self.c["scenarios"]), 16)

    def test_03_transitions_have_implemented_guards_and_reachable_graph(self):
        c = self.c
        states = {s["id"] for s in c["states"]}
        guards = {g["id"]: g for g in c["guards"]}
        adjacency = {s: [] for s in states}
        for t in c["transitions"]:
            self.assertIn(t["from"], states)
            self.assertIn(t["to"], states)
            self.assertIn(t["guard"], guards)
            self.assertTrue(guards[t["guard"]]["fail_closed"])
            self.assertTrue(t["effect"])
            adjacency[t["from"]].append(t["to"])
        seen = {"IDLE"}
        queue = deque(["IDLE"])
        while queue:
            for target in adjacency[queue.popleft()]:
                if target not in seen:
                    seen.add(target)
                    queue.append(target)
        self.assertEqual(seen, states, "[P24A_ORPHAN_STATE] state is unreachable")
        self.assertFalse(adjacency["SIM_TERMINATED_UNRESOLVED"])

    def test_04_custody_is_hard_gated_before_requeue(self):
        c = self.c
        transitions = [t for t in c["transitions"] if t["to"] == "TASK_REQUEUE_PENDING"]
        self.assertEqual({t["guard"] for t in transitions},
                         {"all_tasks_not_picked", "external_custody_verified"},
                         "[P24A_CARGO_TELEPORT] loaded goods cannot automatically return to source")
        self.assertTrue(all(t["from"] == "WAITING_EXTERNAL_HELP" for t in transitions))
        required = {"I04", "I05", "I09", "I11", "I14"}
        self.assertTrue(required <= {i["id"] for i in c["invariants"]})

    def test_05_real_station_guards_and_swap_are_not_optional(self):
        t = self.c["transitions"]
        to_nest = [x for x in t if x["to"] == "DIVERTING_TO_NEST"]
        self.assertEqual({x["guard"] for x in to_nest},
                         {"nest_path_affordable", "low_battery_and_nest_affordable"})
        to_swap = [x for x in t if x["to"] == "SWAPPING_BATTERY"]
        self.assertEqual(len(to_swap), 1)
        self.assertEqual((to_swap[0]["from"], to_swap[0]["guard"]),
                         ("WAITING_FOR_BERTH", "berth_acquired"))
        crediting = [x for x in t if "credit_swap_energy" in x["effect"]]
        done_swap = [x for x in t if x["guard"] == "swap_completed_on_site"]
        self.assertEqual(len(crediting), 1)
        self.assertEqual(crediting, done_swap, "[P24A_MAGIC_CHARGE] on-site energy only")
        self.assertEqual(done_swap[0]["from"], "SWAPPING_BATTERY")
        self.assertIn("release_berth_once", done_swap[0]["effect"])

    def test_06_prohibited_magic_actions_are_all_false(self):
        for name, enabled in self.c["constraints"].items():
            self.assertIs(enabled, False, "[P24A_POLICY_DRIFT] " + name)

    def test_07_future_tests_are_not_claimed_as_passed(self):
        phases = {s["phase"] for s in self.c["scenarios"]}
        self.assertEqual(phases, {"p2.2_current", "future_red"})
        self.assertEqual({s["id"] for s in self.c["scenarios"]
                          if s["phase"] == "p2.2_current"}, {"A01", "A02"})
        future = {s["id"] for s in self.c["scenarios"] if s["phase"] == "future_red"}
        self.assertEqual(future, {"A%02d" % i for i in range(3, 17)})
        self.assertTrue(all(s["stimulus"] and s["expected"] for s in self.c["scenarios"]))

    def test_08_docs_carry_scope_limitations_and_test_binding(self):
        doc = DOC.read_text(encoding="utf-8")
        for term in ("仅设计", "P2.4b", "Task.status", "is_free", "load_time",
                     "Environment.step()", "E0/E1", "P2.2", "P2.3b"):
            self.assertIn(term, doc, "[P24A_MISSING_SCOPE] " + term)
        for id_ in ("I01", "I14", "T01", "T16", "A01", "A16"):
            self.assertTrue(any(s["id"] == id_ for group in
                                ("invariants", "transitions", "scenarios")
                                for s in self.c[group]))

    def test_09_only_p24a_documents_tests_and_workflow_changed(self):
        # Full history checkout is part of CI; fail if production modules or
        # frozen experiment results were accidentally edited on this branch.
        try:
            output = subprocess.check_output(
                ["git", "-C", str(ROOT), "diff", "--name-only",
                 P22 + "...HEAD"], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[P24A_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertTrue(output, "[P24A_EMPTY_CHANGE] no contract committed")
        self.assertEqual(set(output), ALLOWED_CHANGES,
                         "[P24A_SCOPE_VIOLATION] changes differ from four design-only files")


if __name__ == "__main__":
    unittest.main()
