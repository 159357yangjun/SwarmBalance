# TASKUI-SB-UI-01-R1 — Authenticated rule integration

Date: 2026-10-14. Scope: **rule files, scoped engineering guidance, independent CI, and evidence only; no business UI or simulation logic**.

## One authoritative integration baseline

**Target branch and PR base: `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`.** UI-00 static inspection also pinned this exact master SHA. The prior UI-01 Draft PR #42 began at `ci-validation@34cf506ea9b0871fba395e47df6dc96b3a2a21b0`, which differs from master by 33 unrelated commits. R1 deliberately rebuilds the integration as a **single direct descendant of master** and retargets PR #42 to master; no `ci-validation` commits, PR #41 lifecycle modifications, or unmerged UI-00 documentation are imported. `ci-validation` remains an independently maintained CI/logic branch, not an alias of master.

The UI-00 branch includes static audit documents about `console/static` as an independent deliverable. UI-01 relies on the same checked-in application code; it does not claim those unmerged UI-00 reports are accepted or a completed G0/G1 UX requirements map.

## Authentic upstream source

Library path: `/项目/TaskUI/TaskUI-v1.0.0.zip`. ZIP size **31,906 bytes**, archive SHA256 `51a3d064487ba0254282e5c48e6215b5486f9884cdfa3b74a20b1285536d164c` (2026-10-14 materialization). ZIP CRC check passes. Exactly **29 original files** under `TaskUI/` have been retained *unmodified*, with per-file SHA256 recorded in `docs/taskui/SOURCE_SHA256SUMS.txt`. Original package version: **1.0.0**; schema/checker protocol version: **1.0**; this is intentional, not a downgrade. No dependency installation is required for the upstream Python checker/tests (stdlib only).

Layout:

```
TaskUI/                               # exact 29 original upstream files (not handwritten)
console/static/AGENTS.md              # scoped SwarmBalance integration instructions
.github/workflows/taskui-rules.yml    # isolated read-only CI check on PRs to master
docs/taskui/                           # provenance, conflicts, reproducible validation logs
```

The upstream `TaskUI/.github/workflows/taskui.yml` remains in the original package as a reference; it is **not** installed as the repository's workflow. Root `AGENTS.md` is not created or overwritten.

## Actual SwarmBalance web workbench

`console/static/index.html` contains inline Vue 3 global application logic, CSS, native Canvas 2D, Three.js 3D and ECharts. `console/static/spec.html` provides a reference/description view. `console/server.py` is FastAPI, with inline browser `fetch()` API calls; `console/sim_session.py` owns state. The confusing `frontend/` directory primarily contains Python simulation code. There is no verified router, Pinia, Vite or component-file architecture to integrate with. Scoped rules cover the **five in-page navigation areas, global simulation toolbar, map and object inspector, scenario editor/library, runtime snapshots, experiments, historical comparisons**; see the sibling UI-00 function-entry audit for precise static mappings (not merged here).

Do not create a counterfeit `project.taskui.json`: G0 task hierarchy and G1 design evidence require their own review before a project manifest is checked. Later G3 real-use/browser acceptance is separate from passing the static checker.

## Repeatable local and CI validation

Run in repository root:

```bash
sha256sum --check --strict docs/taskui/SOURCE_SHA256SUMS.txt
python -m compileall -q TaskUI/tools TaskUI/tests
python -m unittest discover -s TaskUI/tests -v
python TaskUI/tools/taskui_check.py TaskUI/examples/good.project.taskui.json --strict
python TaskUI/tools/taskui_check.py TaskUI/examples/bad.project.taskui.json --strict # expected exit 1
```

See `VALIDATION_BASELINE.md` for per-command stdout/stderr and exit codes. CI performs the same checks on the exact PR HEAD on Ubuntu with Python 3.10. All of these tests are **rule-integrity checks, not live UI acceptance**. CI from the unrelated `ci-validation` branch has not been asserted successful on master; there are no changes to any preexisting `ci.yml`.
