# TASKUI-SB-UI-01-R1 — Reproducible validation baseline

Local execution UTC: **2026-10-14T12:39:09.621612+00:00**; interpreter: **Python 3.13.5 (linux)**. GitHub CI specifies Python 3.10 on Ubuntu; no inference of remote CI success from local runs.

Source: ChatGPT Library `/项目/TaskUI/TaskUI-v1.0.0.zip` (31,906 bytes, SHA256 `51a3d064487ba0254282e5c48e6215b5486f9884cdfa3b74a20b1285536d164c`). ZIP CRC passes; 29 entries, **29/29 exact byte comparisons** against committed-content candidates. Manifest `docs/taskui/SOURCE_SHA256SUMS.txt` contains the original 29 per-file digests.

Target master baseline: `2ab60c69a806a22d7ba20353dee0571752a0e8e5`. The initial UI-01 PR #42 base `ci-validation` was incorrect relative to UI-00; R1 retargets it to this master baseline and must check the final Git tree and diff.

## Local executed command records

| Command | Actual exit code | Expected | Preserved stdout/stderr |
| --- | ---: | ---: | --- |
| `sha256sum --check --strict docs/taskui/SOURCE_SHA256SUMS.txt` | **0** | 0 | [`source-sha256.log`](validation/source-sha256.log) |
| `python -m compileall -q TaskUI/tools TaskUI/tests` | **0** | 0 | [`compile.log`](validation/compile.log) |
| `python -m unittest discover -s TaskUI/tests -v` | **0** | 0 | [`unittests.log`](validation/unittests.log) |
| `python TaskUI/tools/taskui_check.py TaskUI/examples/good.project.taskui.json --strict` | **0** | 0 | [`good-strict.log`](validation/good-strict.log) |
| `python TaskUI/tools/taskui_check.py TaskUI/examples/bad.project.taskui.json --strict` | **1** | 1 | [`bad-strict.log`](validation/bad-strict.log) |

Unit tests: **9/9 PASS**. Good strict fixture: **PASS, 0 errors and 0 warnings**. Bad strict negative control: **expected FAIL, 10 errors/5 warnings**, exit 1. No upstream checker, schema or test was altered. Output of each command includes the actual process exit code, not inferred PASS. `local-summary.json` records machine-readable metadata.

## Limitations and gates

- No approved project-specific `project.taskui.json` was fabricated; G0/G1 source mapping and UX evidence remain a separate review.
- This validates the **upstream rules and package integrity only**; it does not validate 2D/3D rendering, task usability, keyboard focus, responsiveness, lifecycle, or simulation results.
- GitHub Actions exact-HEAD status and run URLs must be checked **after** the R1 commit. They must not be assumed based on these local logs.
- No nine-job `ci-validation` regression is claimed for master; no production code or existing CI workflow is changed.
## GitHub uploaded-blob integrity cross-check

After writing the exact 29 original upstream files to GitHub, the remote tree at commit `b37df43fe1d91b0cacd4a9b8f4bb8f6d930a60c5` was enumerated and all 29 Git Blob SHA-1 identifiers were checked against local hashes calculated from the original ZIP bytes and preserved in `validation/original-git-blob-sha1.txt`: **29/29 matches**, **0 mismatches**. Against `master@2ab60c...`, the PR diff contained **42 additions, 0 unrelated paths, 0 deletions, 0 modifications to tracked production files** (29 original upstream files + 13 scoped integration/docs/validation files). The subsequent docs-only CI-trigger commit does not touch upstream sources.
