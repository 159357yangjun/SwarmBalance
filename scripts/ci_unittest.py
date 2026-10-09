# -*- coding: utf-8 -*-
"""Fail-closed unittest entry point for SwarmBalance CI.

Each suite runs in a fresh interpreter: console tests depend on import order,
and frontend/ has no __init__.py (so its discovery top-level is frontend).
Skipped tests are *not* successes; the console allowlist is explicit and
changes to test IDs or reason markers require review.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

QUICK = {
    "quick-p2": "console.test_p2_no_name_based_kernel_import",
    "quick-p3": "console.test_p3_no_cross_test_residue",
    "quick-calibration": "console.test_g2teeth_calibration",
}
FULL = {
    "console": ("console", ".", "test_*.py"),
    "experiments": ("experiments", ".", "test_*.py"),
    "frontend": ("frontend", "frontend", "test_*.py"),
    "root": (".", ".", "test_build*.py"),
}
# Baseline: HEAD 2ab60c69 / docs/取证输出/p70_p6_attribution/
# F_console_aggregate_374_skips.log. An expected skip is *still not run*.
CONSOLE_SKIPS = {
    "console.test_c1_lifecycle_gate.C1LifecycleGate.test_1_rules_are_enforced":
        "[OLD_IS_BASELINE_AUDIT_SNAPSHOT]",
    "console.test_c1_lifecycle_gate.C1LifecycleGate.test_4_mutation_face_proves_teeth":
        "mutation",
    "console.test_consistency_observer_zero_drift.ObserverZeroDrift.test_h_attribution_matches_frozen_baseline":
        "[H_SKIPPED_NOT_FROZEN_BASELINE]",
    "console.test_phase1b1_distance_experiment.FullPairedExperiment.test_h0_h1_paired_comparison":
        "SWARM_1B1_FULL=1",
}


def skip_policy_errors(observed, expected):
    """Compare named unittest skips with explicit reason fragments."""
    issues = []
    for test_id, reason in sorted(observed.items()):
        if test_id not in expected:
            issues.append("unexpected skip: %s :: %s" % (test_id, reason))
        elif expected[test_id] not in reason:
            issues.append("changed skip reason: %s :: %s" % (test_id, reason))
    for test_id in sorted(set(expected) - set(observed)):
        issues.append("baseline skip no longer observed (review required): %s" % test_id)
    return issues


def run_group(group):
    loader = unittest.TestLoader()
    if group in QUICK:
        suite = loader.loadTestsFromName(QUICK[group])
    else:
        subdir, top, pattern = FULL[group]
        suite = loader.discover(
            start_dir=str(ROOT / subdir),
            pattern=pattern,
            top_level_dir=str(ROOT / top),
        )
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    observed = {test.id(): reason for test, reason in result.skipped}
    expected = CONSOLE_SKIPS if group == "console" else {}
    issues = skip_policy_errors(observed, expected)
    if result.testsRun == 0:
        issues.append("no tests executed")
    if result.expectedFailures:
        issues.append("unexpected expectedFailures=%d" % len(result.expectedFailures))
    if result.unexpectedSuccesses:
        issues.append("unexpected successes=%d" % len(result.unexpectedSuccesses))
    for test_id, reason in sorted(observed.items()):
        print("[CI_SKIP] %s :: %s" % (test_id, reason), flush=True)
    for issue in issues:
        print("[CI_FAIL] " + issue, flush=True)
    ok = result.wasSuccessful() and not issues
    print(
        "[CI_VERDICT] group=%s ran=%d failed=%d errors=%d skipped=%d "
        "expected_failures=%d unexpected_successes=%d policy_issues=%d status=%s"
        % (group, result.testsRun, len(result.failures), len(result.errors),
           len(result.skipped), len(result.expectedFailures),
           len(result.unexpectedSuccesses), len(issues), "PASS" if ok else "FAIL"),
        flush=True,
    )
    return 0 if ok else 1


def selftest():
    """The guard must actually fail on newly skipped/renamed tests."""
    expected = {"existing": "approved"}
    assert not skip_policy_errors({"existing": "reason: approved"}, expected)
    assert skip_policy_errors({"existing": "different"}, expected)
    assert skip_policy_errors({"existing": "approved", "new": "new skip"}, expected)
    assert skip_policy_errors({}, expected)
    print("[CI_SELFTEST] skip changes rejected; known skip accepted", flush=True)
    return 0



def diagnose_child():
    """Independent discovery census matching _readme_counts._CHILD in one process."""
    import ast
    import collections

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "console"), top_level_dir=str(ROOT),
                            pattern="test_*.py")
    cases = []

    def flatten(s):
        for item in s:
            if isinstance(item, unittest.TestSuite):
                flatten(item)
            else:
                cases.append(item)

    flatten(suite)
    runtime = collections.defaultdict(set)
    for case in cases:
        tid = case.id()
        parts = tid.split(".")
        if len(parts) >= 2 and parts[0] == "console" and parts[1].startswith("test_"):
            runtime[".".join(parts[:2])].add(tid)

    static = {}
    for path in sorted((ROOT / "console").glob("test_*.py")):
        module_name = "console." + path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        classes = {node.name: node for node in tree.body
                   if isinstance(node, ast.ClassDef)}

        def test_case_class(name, seen=None):
            if name not in classes:
                return False
            seen = seen or set()
            if name in seen:
                return False
            seen.add(name)
            node = classes[name]
            for base in node.bases:
                base_name = base.id if isinstance(base, ast.Name) else (
                    base.attr if isinstance(base, ast.Attribute) else "")
                if base_name in {"TestCase", "IsolatedAsyncioTestCase"}:
                    return True
                if test_case_class(base_name, seen):
                    return True
            return False

        static[module_name] = {
            "%s.%s.%s" % (module_name, cls.name, member.name)
            for cls in classes.values() if test_case_class(cls.name)
            for member in cls.body
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            and member.name.startswith("test")
        }
    print("[CENSUS_DIAG] files=%d static_declared=%d runtime=%d loader_errors=%d" %
          (len(static), sum(len(s) for s in static.values()), len(cases),
           len(loader.errors)), flush=True)
    for name in sorted(set(static) | set(runtime)):
        observed = runtime[name]
        defined = static.get(name, set())
        print("[CENSUS_MODULE] %s source=%d discovered=%d missing=%d extra=%d" %
              (name, len(defined), len(observed),
               len(defined - observed), len(observed - defined)), flush=True)
        for case_id in sorted(defined - observed):
            print("[CENSUS_MISSING] " + case_id, flush=True)
        for case_id in sorted(observed - defined):
            print("[CENSUS_EXTRA] " + case_id, flush=True)
    for item in loader.errors:
        print("[CENSUS_IMPORT_ERROR] " + item[-4000:], flush=True)
    return 0


def diagnose():
    """Reproduce the count tool's clean environment rather than the parent CI."""
    from console._preflight import isolated_env
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--diagnose-child"],
        cwd=str(ROOT), env=isolated_env(), check=False,
    )
    return proc.returncode


def main(argv):
    if len(argv) != 1:
        print("Usage: python scripts/ci_unittest.py {selftest|quick|full|_group NAME}")
        return 2
    mode = argv[0]
    if mode == "diagnose":
        return diagnose()
    if mode == "selftest":
        return selftest()
    groups = tuple(QUICK) if mode == "quick" else tuple(FULL) if mode == "full" else ()
    if not groups:
        print("Unknown mode: " + mode)
        return 2
    failed = []
    for group in groups:
        print("[CI_START] " + group, flush=True)
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--group", group],
            cwd=str(ROOT), env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            check=False,
        )
        if proc.returncode != 0:
            failed.append(group)
    print("[CI_SUMMARY] mode=%s groups=%d failed=%s" %
          (mode, len(groups), ",".join(failed) or "none"), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--diagnose-child":
        sys.exit(diagnose_child())
    if len(sys.argv) == 3 and sys.argv[1] == "--group":
        name = sys.argv[2]
        sys.exit(run_group(name) if name in QUICK or name in FULL else 2)
    sys.exit(main(sys.argv[1:]))
