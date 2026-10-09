# P1 CI full-suite first execution and remediation (2026-10-09)

Source: GitHub Actions run 37942695485, commit cec14a0e872511e1da12f6b7876c9707dbe9f6ae.
This is an **observed failed run**, not a passing baseline.

| Group | Actually ran | Failures | Errors | Skips | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| console | 374 | 2 | 1 | 4 | FAIL |
| experiments | 32 | 0 | 0 | 0 | PASS |
| frontend | 21 | 0 | 0 | 0 | PASS |
| root | 3 | 0 | 0 | 0 | PASS |

Whole run conclusion: **failure**. Evidence: console log `[CI_VERDICT] group=console ran=374 failed=2 errors=1 skipped=4 policy_issues=0 status=FAIL`, not README discovery counts.

The four console skips are **not executed**; they match the explicit policy in `scripts/ci_unittest.py`. Do not conflate "four skips explicitly accounted for" with "four tests passed."

## Three failing console tests

1. `console.test_dead_charging_fields.DeadChargingFieldTests.test_classifier_is_not_vacuous`: `os.path.relpath` on Windows crosses `C:` TEMP to `D:` workspace and raises `ValueError`. Fix retains repository-relative references for in-tree files and absolute normalized paths for external fixtures.
2. `console.test_compare_gate.CitationIntegrityTests.test_coverage_is_printed_not_just_asserted`: test invoked `_citations.main(["--verify"])` and unintentionally enabled local-only rewrite-object auditing, which cannot run in a fresh clone. Fix passes explicit `--portable-rewrite` while keeping other documentation checks.
3. `console.test_frozen_artifact_source_pins.FrozenArtifactSourcePin.test_C_declaration_requires_the_named_artifact`: one historical CHANGELOG declaration names a now-unreferenced artifact; original assertion demanded every archival declaration mention a *currently referenced* directory. Fix ensures each declaration explicitly names **its own** artifact and marker on the same line, preserves the two-line negative control, and verifies current referenced artifacts still have specific declarations.

A first repair run encountered an additional source edit formatting error (`IndentationError` in `test_compare_gate.py`), which was corrected. The subsequent CI step `Recheck three full-suite regression failures` passed, and the compiler gate passed.

**Pending verification:** repeat the entire console 374-test suite under the same strict skip policy to determine whether any further failures remain. This document records why the full-suite replay is triggered; it does **not** pre-claim success for the replay.
