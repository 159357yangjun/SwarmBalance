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
P24A_HEAD = "7ca10647201432062fbfd366fccba48027dbdd24"
B1_HEAD = "fd8a001b09cb85b6875426d0e30532ee6e6831ac"
B2_HEAD = "1601a36e7fb560b7126d13133d820a7bb4c60fe6"
B3A_HEAD = "b10b49e5e69a2d2b9986e20bf8b8b853460ec4f0"
B3B_HEAD = "25a77553c710c06cc105986f140d66ba5c5c6c6d"
B3C_HEAD = "fca9ebfeb2413d8b396f20c10c98ddd50d2fcd47"
B4_HEAD = "e669075e120d3e646ec7f0623346608736f26966"
B4B_HEAD = "69ea639f12a89141adc881ae614e511a72ede7d4"
B4C_HEAD = "42cf220143caff5fe12e91c0731279ed4486272e"
B4D_HEAD = "47e64cac22dc5d1476f52a47b3ffd4f3d5ef9002"
B4E_HEAD = "cea965f9b66e26473d4d1190a3f70c6cc8b7c61f"
B5A_HEAD = "ba3eac83151928a080d6c2abac40bdc4b245c704"
B5B_HEAD = "ac3660154e4729f9a56561ca312dc0cd94846f8b"
B5C_HEAD = "4f5fc4639fe4b45296b6720454e5d946249bdcc1"
B5D_HEAD = "907735e82591fff60840e21a7dcafb2a861ece71"
B5E_HEAD = "d32f11137f26c18e3c7f4e0a5ee925cd7d561fe3"
B5F_HEAD = "628f148e54fa3530e07c84e685f6ba4d7f27eece"
B5G_HEAD = "121d94ab208869e417a89b2844563a26b8e7e101"
AUDIT_HEAD = "b23a8e4362260acb6a0df330fbd8665581d0e567"
R1_ALLOWED_CHANGES = {
    "console/test_config_keys_coverage.py",
    ".github/workflows/research-r1-energy-readiness.yml",
    "docs/RESEARCH_R1_ENERGY_UNITS_READINESS.md",
    "experiments/reproducibility.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_research_r1_energy_units_red.py",
}
AUDIT_ALLOWED_CHANGES = {
    "README.md",
    ".github/workflows/model-provenance-audit.yml",
    "docs/P2_4B_B5_SECURITY_AND_RESEARCH_GATES.md",
    "experiments/reproducibility.py",
    "experiments/test_model_provenance_gate.py",
    "scripts/p2_4a_state_contract_test.py",
}
B5G_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b5g-serialized-custody.yml",
    "console/custody_queue_bridge.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b5g_serialized_queue_red.py",
}
B5F_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b5f-queue-reconcile.yml",
    "console/custody_queue_bridge.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b5f_queue_reconcile_red.py",
}
B5E_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b5e-transactional-custody.yml",
    "console/custody_transaction.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b5d_custody_journal_red.py",
    "scripts/test_p2_4b_b5e_transactional_custody_red.py",
}
B5D_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b5d-custody-journal.yml",
    "console/custody_journal.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b5d_custody_journal_red.py",
}
B5C_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b5c-mixed-chain-custody.yml",
    "frontend/environment.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b5c_mixed_chain_custody_red.py",
}
B5B_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b5b-external-custody.yml",
    "frontend/environment.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b5b_external_custody_red.py",
}
B5A_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b5a-cargo-custody.yml",
    "docs/数据来源与可追溯性登记表.md",  # actual relocated anchors only
    "frontend/environment.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b5a_cargo_custody_red.py",
}
# B4e is a strict independent child; do not reinterpret B4d's frozen
# six-file boundary as a diff to the HEAD of every descendant.
B4E_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b4e-end-to-end-conservation.yml",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b4e_end_to_end_conservation.py",
}
B4D_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b4d-inflight-wind-energy.yml",
    "docs/P2_4B_B4D_INFLIGHT_WIND_EVIDENCE.md",
    "docs/数据来源与可追溯性登记表.md",
    "frontend/environment.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b4d_inflight_wind_energy.py",
}

B4C_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b4c-held-route-requote.yml",
    "docs/P2_4B_B4C_HELD_REQUOTE_EVIDENCE.md",
    "docs/数据来源与可追溯性登记表.md",
    "frontend/environment.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b4c_held_route_requote.py",
}

B4B_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b4b-auto-target-red.yml",
    "docs/P2_4B_B4B_AUTO_TARGET_EVIDENCE.md",
    "docs/数据来源与可追溯性登记表.md",
    "frontend/drone.py",
    "frontend/environment.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b4b_auto_target_closure.py",
}

B4_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b4-auto-planned-nest.yml",
    "docs/P2_4B_B4_AUTO_PLANNED_NEST_EVIDENCE.md",
    "frontend/drone.py",
    "frontend/environment.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b4_auto_planned_nest.py",
}

B3C_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b3c-target-station.yml",
    "docs/P2_4B_B3C_STATION_IDENTITY_EVIDENCE.md",
    "docs/数据来源与可追溯性登记表.md",
    "frontend/drone.py",
    "frontend/environment.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b3c_target_station.py",
}

B3B_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b3b-planned-charge-route.yml",
    "docs/数据来源与可追溯性登记表.md",  # 9 exact relocated environment.py citation anchors
    "docs/P2_4B_B3B_PLANNED_CHARGE_EXECUTION_EVIDENCE.md",
    "frontend/environment.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b3b_planned_charge_route.py",
}

B3A_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b3a-planned-station-quote.yml",
    "docs/P2_4B_B3A_PLANNED_ROUTE_WH_EVIDENCE.md",
    "frontend/environment.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b3_planned_station_quote.py",
}

B2_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b2-station-energy.yml",
    "docs/P2_4B_B2_DIRECT_STATION_ENERGY_EVIDENCE.md",
    "docs/数据来源与可追溯性登记表.md",
    "frontend/drone.py",
    "scripts/p2_4a_state_contract_test.py",
    "scripts/test_p2_4b_b2_station_energy_gate.py",
}

B1_ALLOWED_CHANGES = {
    ".github/workflows/p2-4b-b1-energy-quote.yml",
    "docs/P2_4B_B1_ENERGY_QUOTE_EVIDENCE.md",
    "docs/数据来源与可追溯性登记表.md",  # correct migrated code-line anchors only
    "console/test_c4_cargo_truth_scan_gate.py",  # audited bounded-capacity exemption moved with quote
    "frontend/drone.py",
    "scripts/test_p2_4b_b1_energy_quote.py",
    "scripts/p2_4a_state_contract_test.py",  # chained slice scope guard
}

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
        # Historical *immutable* design slice; descendants may implement code.
        # The P2.4a four-file gate must remain strict and never inspect a
        # broader future HEAD as though it were still design-only.
        try:
            output = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false", "diff", "--name-only",
                 P22 + "..." + P24A_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[P24A_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertTrue(output, "[P24A_EMPTY_CHANGE] no contract committed")
        self.assertEqual(set(output), ALLOWED_CHANGES,
                         "[P24A_SCOPE_VIOLATION] exactly four design files required")

    def test_10_only_b1_energy_quote_scope_changed(self):
        # New, equally strict HEAD gate covers every new B1 file, including
        # this anchored historical-slice adaptation. Fail on changes to
        # scheduler/config/frozen archives or unapproved files.
        try:
            output = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false", "diff", "--name-only",
                 P24A_HEAD + "..." + B1_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B1_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(output), B1_ALLOWED_CHANGES,
                         "[B1_SCOPE_VIOLATION] only listed energy-quote / test files")
    def test_11_only_b2_direct_station_gate_scope_changed(self):
        # Do not broaden B1's immutable historical scope to accept B2.
        # Every current B2 file still requires an exact whitelist match.
        try:
            output = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false", "diff", "--name-only",
                 B1_HEAD + "..." + B2_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B2_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(output), B2_ALLOWED_CHANGES,
                         "[B2_SCOPE_VIOLATION] exact B2 allowlist only")

    def test_12_only_b3a_route_quote_scope_changed(self):
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B2_HEAD + "..." + B3A_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B3A_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B3A_ALLOWED_CHANGES,
                         "[B3A_SCOPE_VIOLATION] exact route quote allowlist only")

    def test_13_only_b3b_planned_execution_scope_changed(self):
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B3A_HEAD + "..." + B3B_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B3B_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B3B_ALLOWED_CHANGES,
                         "[B3B_SCOPE_VIOLATION] exact manual-planned-route allowlist only")

    def test_14_only_b3c_target_identity_and_berth_scope_changed(self):
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B3B_HEAD + "..." + B3C_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B3C_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B3C_ALLOWED_CHANGES,
                         "[B3C_SCOPE_VIOLATION] strict seven-file station guard only")

    def test_15_only_b4_auto_planned_energy_scope_changed(self):
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B3C_HEAD + "..." + B4_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B4_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B4_ALLOWED_CHANGES,
                         "[B4_SCOPE_VIOLATION] exact automatic route six files only")

    def test_16_only_b4b_target_identity_scope_changed(self):
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B4_HEAD + "..." + B4B_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B4B_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B4B_ALLOWED_CHANGES,
                         "[B4B_SCOPE_VIOLATION] exactly seven target-identity files")

    def test_17_only_b4c_held_requote_scope_changed(self):
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B4B_HEAD + "..." + B4C_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B4C_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B4C_ALLOWED_CHANGES,
                         "[B4C_SCOPE_VIOLATION] exact six-file held route re-quote")

    def test_18_only_b4d_inflight_wind_scope_changed(self):
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B4C_HEAD + "..." + B4D_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B4D_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B4D_ALLOWED_CHANGES,
                         "[B4D_SCOPE_VIOLATION] exact six-file in-flight wind boundary")

    def test_19_only_b4e_end_to_end_conservation_scope_changed(self):
        # The old B4d slice is immutable; B4e gets its OWN exact diff gate.
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B4D_HEAD + "..." + B4E_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B4E_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B4E_ALLOWED_CHANGES,
                         "[B4E_SCOPE_VIOLATION] exact three-file B4e experimental test boundary")

    def test_20_only_b5a_picked_cargo_fault_scope_changed(self):
        # The accepted B4e three-file slice remains immutable. B5a must
        # independently account for EVERY changed file without weakening it.
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B4E_HEAD + "..." + B5A_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B5A_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B5A_ALLOWED_CHANGES,
                         "[B5A_SCOPE_VIOLATION] exact B5a five-file experimental boundary")

    def test_21_only_b5b_external_handoff_scope_changed(self):
        # Preserve B5a's exact historical five-file slice and independently
        # enforce every B5b modification; never widen old allowlists.
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B5A_HEAD + "..." + B5B_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B5B_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B5B_ALLOWED_CHANGES,
                         "[B5B_SCOPE_VIOLATION] exact four-file B5b experimental boundary")

    def test_22_only_b5c_atomic_mixed_manifest_scope_changed(self):
        # B5b remains exactly frozen at its accepted four-file HEAD.
        # B5c gets a separate, strict four-file Git diff equality gate.
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B5B_HEAD + "..." + B5C_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B5C_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B5C_ALLOWED_CHANGES,
                         "[B5C_SCOPE_VIOLATION] exact four-file B5c experimental boundary")

    def test_23_only_b5d_durable_journal_scope_changed(self):
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B5C_HEAD + "..." + B5D_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B5D_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B5D_ALLOWED_CHANGES,
                         "[B5D_SCOPE_VIOLATION] exact four-file isolated journal boundary")

    def test_24_only_b5e_transactional_custody_scope_changed(self):
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B5D_HEAD + "..." + B5E_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B5E_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B5E_ALLOWED_CHANGES,
                         "[B5E_SCOPE_VIOLATION] exact five-file transaction boundary")


    def test_25_only_b5f_sqlite_queue_bridge_scope_changed(self):
        # Never reinterpret historical B5e's strict five-file change set
        # against a moving B5f HEAD; B5f gets an independent exact gate.
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B5E_HEAD + "..." + B5F_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B5F_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B5F_ALLOWED_CHANGES,
                         "[B5F_SCOPE_VIOLATION] exact four-file B5f boundary")

    def test_26_only_b5g_serialized_sqlite_scope_changed(self):
        # Accepted B5f slice remains immutable even with B5g's own edits.
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B5F_HEAD + "..." + B5G_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[B5G_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), B5G_ALLOWED_CHANGES,
                         "[B5G_SCOPE_VIOLATION] exact four-file B5g experimental boundary")

    def test_27_only_research_provenance_audit_scope_changed(self):
        # Audit is its own slice. Preserve B5g's immutable four-file gate.
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", B5G_HEAD + "..." + AUDIT_HEAD], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[AUD_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), AUDIT_ALLOWED_CHANGES,
                         "[AUD_SCOPE_VIOLATION] exact six-file research audit boundary")

    def test_28_only_r1_energy_units_and_provenance_scope_changed(self):
        try:
            names = subprocess.check_output(
                ["git", "-C", str(ROOT), "-c", "core.quotePath=false",
                 "diff", "--name-only", AUDIT_HEAD + "...HEAD"], text=True).splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.fail("[R1_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(names), R1_ALLOWED_CHANGES,
                         "[R1_SCOPE_VIOLATION] exact six-file R1 and console-corpus boundary")


if __name__ == "__main__":
    unittest.main()
