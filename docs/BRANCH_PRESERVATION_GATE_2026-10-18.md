# SwarmBalance branch preservation gate (2026-10-18)

**STATUS: HOLD — DO NOT DELETE ALL NON-MASTER BRANCHES.**

This is a live GitHub compare inventory against `master` as checked on 2026-10-18. `ahead_by` counts commits not reachable from master, **not unique features or lost patches**. No branch source is preserved by this document alone. Merge/cherry-pick, copy files with clear provenance, or create verified durable Git tags/refs **before** deleting branches. Recheck against latest master at deletion time.

* Repository: 159357yangjun/SwarmBalance
* Branches inspected: 67 including master; non-master: 66; non-master with unique commit history: 36; fully reachable: 30.
* Already merged: PR #65 (research), PR #66 (persistent MVP backend). Separate legacy MVP-01 workbench, TaskUI drafts, ARCH/CONTRACT proposals, experimental alternative branches are not collectively accepted into master.
* Do not promote HOLD / NO-FREEZE proposal documents to accepted runtime contracts. Keep RED/negative experiments and frozen evidence separate from production behavior.

| Remote branch | Ahead of master | Deletion ruling |
|---|---:|---|
| `audit/l0-core-logic-readonly-20261012` | 4 | BLOCKED: independently reachable history; preserve before deletion |
| `audit/model-provenance-and-paired-plan-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `ci-validation` | 0 | Potentially safe *after ref/CI recheck* |
| `docs/simulation-consistency-vv-guide-20261012` | 1 | BLOCKED: independently reachable history; preserve before deletion |
| `governance/multi-agent-protocol-v1` | 6 | BLOCKED: independently reachable history; preserve before deletion |
| `integration/master-consolidation-20261018` | 0 | Potentially safe *after ref/CI recheck* |
| `integration/research-mainline-20261018` | 0 | Potentially safe *after ref/CI recheck* |
| `logic/l1-task-lifecycle-delivery-proof-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `mvp01-backend` | 1 | BLOCKED: independently reachable history; preserve before deletion |
| `mvp01-integration` | 3 | BLOCKED: independently reachable history; preserve before deletion |
| `mvp01-workbench` | 3 | BLOCKED: independently reachable history; preserve before deletion |
| `p1-5-evidence-freeze-v1` | 1 | BLOCKED: independently reachable history; preserve before deletion |
| `p1-b-onboard-energy-experiment` | 0 | Potentially safe *after ref/CI recheck* |
| `p1-b-paired-analysis-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p1-b-pressure-event-validation` | 0 | Potentially safe *after ref/CI recheck* |
| `p1-b-shadow-ledger-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p1-b-stress-grid-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-1-low-energy-audit-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-2-flight-energy-gate-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-2-g2-root-cause-diagnostic-v1` | 8 | BLOCKED: independently reachable history; preserve before deletion |
| `p2-3-flight-feasibility-impact-v1` | 1 | BLOCKED: independently reachable history; preserve before deletion |
| `p2-3b-forced-depletion-v1` | 2 | BLOCKED: independently reachable history; preserve before deletion |
| `p2-3b-low-battery-trigger-v1` | 2 | BLOCKED: independently reachable history; preserve before deletion |
| `p2-4a-recovery-state-contract-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b1-energy-quote-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b2-station-reachability-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b3-planned-station-quote-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b3b-planned-charge-route-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b3c-station-identity-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b4-auto-planned-nest-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b4b-auto-station-identity-v1` | 9 | BLOCKED: independently reachable history; preserve before deletion |
| `p2-4b-b4b-auto-target-closure-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b4c-held-route-requote-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b4c-midflight-wind-guard-v1` | 18 | BLOCKED: independently reachable history; preserve before deletion |
| `p2-4b-b4d-inflight-wind-energy-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b4e-end-to-end-conservation-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b5a-cargo-custody-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b5b-external-custody-handoff-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b5c-mixed-chain-custody-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b5d-custody-journal-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b5d-durable-custody-journal-red-v1` | 4 | BLOCKED: independently reachable history; preserve before deletion |
| `p2-4b-b5e-journaled-handoff-red-v1` | 8 | BLOCKED: independently reachable history; preserve before deletion |
| `p2-4b-b5e-transactional-custody-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b5f-sqlite-queue-reconcile-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `p2-4b-b5g-serialized-custody-reconcile-red-v1` | 0 | Potentially safe *after ref/CI recheck* |
| `platform/arch-01-world` | 1 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/arch-02-harness` | 12 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/arch-03-components` | 6 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/arch-04-migration` | 1 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/arch-05-r2-review` | 2 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/arch-05-r3-contract-review` | 3 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/arch-05-review` | 1 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/arch-06-freeze-decision` | 3 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/arch-exp-01-experiments` | 2 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/arch-vve-01-credibility` | 2 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/contract-01-state-events` | 14 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/contract-02-component-runtime` | 12 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/contract-03-experiment-rng` | 16 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/contract-04-results-evidence` | 25 | BLOCKED: independently reachable history; preserve before deletion |
| `platform/contract-05-implementation-gates` | 6 | BLOCKED: independently reachable history; preserve before deletion |
| `research/r1-energy-units-and-accounting-provenance-v1` | 9 | BLOCKED: independently reachable history; preserve before deletion |
| `research/r2-flight-data-source-feasibility-v1` | 5 | BLOCKED: independently reachable history; preserve before deletion |
| `ui/taskui-00-audit` | 6 | BLOCKED: independently reachable history; preserve before deletion |
| `ui/taskui-01-rules` | 2 | BLOCKED: independently reachable history; preserve before deletion |
| `ui/taskui-02-requirements` | 6 | BLOCKED: independently reachable history; preserve before deletion |
| `ui/taskui-b01-cross-review` | 1 | BLOCKED: independently reachable history; preserve before deletion |

## Release gate

1. Record exact tip SHA for every ahead branch, pin restore tags or incorporate all commits/artifacts into master; cross-check no lost history.
2. Carry forward incompatible work as isolated, clearly labeled archive assets; do not overwrite active simulation modules or the 2D/3D console.
3. Run mainline CI and integration tests at final exact master HEAD; verify old experiment data and baseline source hashes.
4. Only then delete verified redundant branches. Do not delete everything merely because this inventory exists.
