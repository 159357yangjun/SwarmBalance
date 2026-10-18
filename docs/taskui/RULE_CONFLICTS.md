# UI-01-R1 — Rule and repository conflict register

Reviewed 2026-10-14 against authoritative **master@2ab60c69a806a22d7ba20353dee0571752a0e8e5** and the untouched original TaskUI ZIP.

| ID | Actual fact / conflict | R1 resolution | Status |
|---|---|---|---|
| C01 | UI-00 uses `master`, while UI-01 staging PR #42 previously used `ci-validation` (33 extra commits). | Recreate UI-01 commit directly atop master and retarget Draft PR #42 to master; do not merge PR #41. | Resolved by R1 ref/tree verification |
| C02 | No root `AGENTS.md` in master; upstream archive has `TaskUI/AGENTS.md`. | Preserve upstream verbatim, add only `console/static/AGENTS.md`; do not create/overwrite root. | Resolved |
| C03 | `ci-validation` has its own Windows Python-3.10 CI and source/history tests; master does not contain that same workflow at the pinned SHA. | Do not replace, edit or inherit `ci-validation` workflow. Independent narrow TaskUI workflow runs on master PR; don't represent it as full simulator regression. | Separated, existing CI untouched |
| C04 | Upstream `TaskUI/.github/workflows/taskui.yml` is sample workflow content, nested inside package. | Keep bytes in original location; provide separate `.github/workflows/taskui-rules.yml` for integration. | Resolved |
| C05 | `frontend/` is Python simulation, whereas browser UI lives in `console/static/index.html`. | Scope browser instructions under `console/static`, forbid simulation, server, and UI business file changes. | Resolved |
| C06 | Single inline Vue + ECharts + Three.js HTML frontend, no verified Vue Router/Vite/Pinia. | Rules refer to actual five navigation areas, controls and API boundaries; no invented frontend scaffolding. | Resolved |
| C07 | Source package 1.0.0 vs manifest/checker protocol 1.0. | Record separately; never modify upstream values to force cosmetic version match. | Resolved |
| C08 | Upstream tests/good manifest can pass without checking actual SwarmBalance task usability. | Project G0/G1 manifest must be based on approved evidence; G3 requires browser tasks, focus/error/viewport observations. | Open design/UX gate, not an integration defect |
| C09 | Master differs from `ci-validation` and PR #41 in lifecycle/experiment behavior. | No changes/imports to simulation, API, scheduling, config, frozen datasets or results in UI-01-R1. | Protected |
| C10 | CI full project regression is on an independent validation branch. | New read-only rule-only job does not claim or bypass 9-job regression; future behavioral changes require separately authorized baseline. | No preexisting CI modification |

Never claim the TaskUI static manifest checker constitutes a usability or simulation integration test.
