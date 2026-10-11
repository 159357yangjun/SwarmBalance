# P2.2 – minimal flight energy gate contract (RED witness first)

**Requirement:** A simulated drone cannot advance a proposed 1-second flight leg it cannot fully pay for, whether the leg reaches a waypoint or is an intermediate part of a longer leg.

Scope: existing `Drone.update()` / `Environment.step()`, both assigned(default) and onboard(opt-in) energy accounting. Preserve the original `consume_battery()` public ledger semantics for direct callers: `required=debited+shortfall`; do not change the load formula.

## Gate transitions

| State | Condition | Outcome |
|---|---|---|
| READY | required for next actual movement <= available battery | commit exactly original movement, debit via original `consume_battery`, continue actual service events |
| READY/BLOCKED | required > available | **do not move**, consume zero Wh, **do not pop** waypoint or synthesize service, retain task and route, make drone unavailable for new assignment, set explicit `flight_energy_blocked` and `energy_insufficient`. Record attempted `required`, 0 debited, `shortfall=required` to conserve `required=debited+shortfall` |
| BLOCKED | no replenishment | repeat blocked safely; no invisible free flight |
| BLOCKED | battery has been externally replenished sufficiently | clear block flag; continue precisely original scheduled route and normal debit; no automatic battery creation |
| OUT OF SERVICE | pre-existing fault flag | freeze as existing behavior |
| SWAPPING | pre-existing swap control at a station | existing swapping semantics; gate does not grant a remote instant swap |

**Not claimed:** safe landing, finding/reaching a charger, automatic task requeue, reserve energy for return, or physical airframe behavior. A blocked drone may need manual intervention. These are later, separately approved policies.

**RED witness:** on P2.1 base `806d07653af52b83202ba232cb1f3e88dd9b7901`, insufficient 0.2 Wh for 20m/1.2Wh moves physically 20m anyway. Run strict unittest and record actual failure before minimal fix. NEVER xfail, weaken or skip test.
