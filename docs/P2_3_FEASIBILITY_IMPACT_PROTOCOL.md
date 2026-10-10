# P2.3 – paired physical feasibility policy impact experiment

**Objective:** compare real Greedy simulator source before versus after P2.2, using the SAME task arrivals and configuration; measure the operational cost of no longer flying physically impossible, unpaid legs. This is **not** a real-aircraft safety validation.

## Immutable comparisons

- Baseline P2.1 actual repository SHA: `806d07653af52b83202ba232cb1f3e88dd9b7901` (no flight-energy feasibility gate).
- P2.2 source SHA: `5bcc6cb9661dc250c11c578acbacc32c8b0d6f4f` (pre-step gate).
- Both are separate Git worktrees, not one simulator with the gate disabled, nor a Python mock that changes debit rules.
- **Assigned-load accounting only**. B experimental `onboard` model remains opt-in/off; any results for B require another explicit experiment.
- Identical OSM, realistic generator and config: duration 3600 simulated seconds, fleet 10, total-task cap 500, arrival interval factors normal=1.0/elevated=0.65/high=0.4.
- Ten identical P1.2 seeds 51001–51010; the `TaskGenerator` runs without dispatch to create a fixed exogenous order tape; simulator versions receive the identical hashed tape.
- The baseline replay must match the committed P1.3 60-row CSV's **assigned** rows for each seed in generated count, completed count, total distance, energy debited, average delay, swaps, config SHA and tape SHA. If not, stop rather than label data comparable.
- 3 profiles × 10 seeds × 2 immutable code revisions = 60 full real `Environment.step()` / Greedy episodes.

## Measurement

For the old source, instrument the original `Drone.consume_battery` return and `last_energy_shortfall_wh` read-only to count leg events where physical movement was simulated despite inability to debit total required Wh. For new source, instrument `Drone._flight_step_feasible` read-only, counting blocked next-leg attempts and unique affected drones. For both, preserve the original movement, battery bookkeeping and Greedy decisions.

Record at least completion / generated, unfinished, delay (completed-only), timeouts (completed-only), actual debited energy, swaps, flight distance, queue peak, old unpaid leg events, new blocked next-step attempts and affected drones. **Blocked attempts and drone-seconds are not distinct tasks**, and cannot be interpreted as safe-landing statistics. No emergency recovery algorithm is simulated.

## Gates and interpretation

- All 30 `profile,seed` unique keys and all 60 `profile,seed,version` episode keys must be present; no synthesised/fake rows, no missing runs, no seed or task tape drift.
- New-code simulation must never observe `consume_battery` with an energy shortfall after a positive flight step; any incident is a hard failure.
- The positive or negative differences are exploratory, not claims of non-inferiority or aircraft flight safety.
- A fall in completion can be **correct** if former delivery depended on unpaid/infeasible movement.
- This experiment does **not** implement auto-landing, reachable stations, reserve-to-home, automatic task requeue, or engine failure recovery.
- Report and CSV are uploaded to Actions artifacts (30-day retention) for evidence archiving. Existing E0/E1 and PRs #1–#9 remain untouched; project production defaults remain unchanged.

## Branch and workflow

P2.3 is a Draft PR containing only this doc, an experiment driver and its GitHub workflow. It targets `ci-validation` temporarily to launch separate experimental workflow, and should return to `p2-2-flight-energy-gate-v1` after successful full validation. **Do not merge** without independent permission.
