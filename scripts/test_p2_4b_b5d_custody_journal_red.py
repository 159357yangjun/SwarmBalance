# -*- coding: utf-8 -*-
"""B5d RED-first persistence contract, independent of volatile Environment memory.

Journal is operator-attestation audit evidence only; NEVER a claim of verified
physical cargo recovery and NEVER a complete Environment restore checkpoint.
"""
import tempfile
import unittest
from pathlib import Path

from console.custody_journal import CustodyJournal


class CustodyJournalRed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "custody.jsonl"

    def event(self, event_id="receipt-001", task_id="task-001", mass=0.5):
        return {
            "event_id": event_id, "task_id": task_id, "operator_id": "operator-001",
            "evidence_ref": "signed-receipt-001",
            "receipt_position": [20.0, 0.0], "received_weight_kg": mass,
            "disposition": "returned_to_original_source",
            "custody_mode": "operator_attestation_not_physical_verification",
            "load_time": 1.0, "drone_id": "0",
            "drone_position_at_handoff": [40.0, 0.0],
        }

    def test_B5d_01_reopen_new_process_reads_same_committed_receipt(self):
        journal = CustodyJournal(self.path)
        self.assertTrue(journal.append(self.event())["changed"])
        new_process = CustodyJournal(self.path)
        self.assertEqual(new_process.get("receipt-001")["task_id"], "task-001")
        self.assertEqual(new_process.get("receipt-001")["received_weight_kg"], 0.5)
        self.assertEqual(new_process.get("receipt-001")["custody_mode"],
                         "operator_attestation_not_physical_verification")

    def test_B5d_02_duplicate_identical_is_noop_conflicting_is_rejected(self):
        j = CustodyJournal(self.path)
        self.assertTrue(j.append(self.event())["changed"])
        self.assertFalse(CustodyJournal(self.path).append(self.event())["changed"])
        with self.assertRaisesRegex(ValueError, "B5D_EVENT_CONFLICT"):
            CustodyJournal(self.path).append(self.event(mass=0.9))
        self.assertEqual(len(CustodyJournal(self.path).all_events()), 1)

    def test_B5d_03_truncated_tail_must_fail_closed_and_preserve_file(self):
        CustodyJournal(self.path).append(self.event())
        with self.path.open("ab") as f:
            f.write(b'{"seq": 2, "event":')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "B5D_JOURNAL_CORRUPT"):
            CustodyJournal(self.path).all_events()
        self.assertEqual(self.path.read_bytes(), before)

    def test_B5d_04_modified_old_payload_fails_integrity_validation(self):
        CustodyJournal(self.path).append(self.event())
        original = self.path.read_bytes()
        mutated = original.replace(b"task-001", b"task-999")
        self.assertNotEqual(original, mutated)
        self.path.write_bytes(mutated)
        with self.assertRaisesRegex(ValueError, "B5D_JOURNAL_CORRUPT"):
            CustodyJournal(self.path).all_events()

    def test_B5d_05_bad_attestation_fails_before_file_created(self):
        bad = self.event()
        bad["received_weight_kg"] = float("nan")
        with self.assertRaisesRegex(ValueError, "B5D_INVALID_EVENT"):
            CustodyJournal(self.path).append(bad)
        self.assertFalse(self.path.exists())

    def test_B5d_06_two_sequential_events_retain_order_and_provenance(self):
        j = CustodyJournal(self.path)
        self.assertTrue(j.append(self.event())["changed"])
        second = self.event(event_id="receipt-002", task_id="task-002")
        second["evidence_ref"] = "signed-receipt-002"
        self.assertTrue(j.append(second)["changed"])
        fresh = CustodyJournal(self.path)
        self.assertEqual([e["event_id"] for e in fresh.all_events()],
                         ["receipt-001", "receipt-002"])
        self.assertEqual(len(fresh.all_events()), 2)


    def test_B5d_07_exact_isolated_four_file_scope(self):
        import subprocess
        root = Path(__file__).resolve().parents[1]
        try:
            changed = subprocess.check_output([
                "git", "-C", str(root), "-c", "core.quotePath=false",
                "diff", "--name-only",
                "4f5fc4639fe4b45296b6720454e5d946249bdcc1...907735e82591fff60840e21a7dcafb2a861ece71"
            ], text=True).splitlines()
        except (OSError, subprocess.CalledProcessError) as exc:
            self.fail("[B5D_GIT_DIFF_NOT_VERIFIED] " + repr(exc))
        self.assertEqual(set(changed), {
            ".github/workflows/p2-4b-b5d-custody-journal.yml",
            "console/custody_journal.py",
            "scripts/p2_4a_state_contract_test.py",
            "scripts/test_p2_4b_b5d_custody_journal_red.py",
        }, "[B5D_SCOPE_VIOLATION] exact four-file isolated journal boundary")


if __name__ == "__main__":
    unittest.main()
