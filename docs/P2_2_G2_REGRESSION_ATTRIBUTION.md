# P2.2 G2 regression: attribution and isolated fixture

## Immutable red/green evidence

- P2.1 baseline: `806d07653af52b83202ba232cb1f3e88dd9b7901` — G2TEETH **PASS**.
- P2.2 implementation: `5bcc6cb9661dc250c11c578acbacc32c8b0d6f4f` — G2TEETH **FAIL**.
- Both use exact identical G2 test Git blob `0e0512495e82048044710182c31405e5a897b8cb`.
- Evidence: https://github.com/159357yangjun/SwarmBalance/actions/runs/38036357910.
- Baseline optimize counts, 6 versus 10 drones: 1909 / 6 (0.31%).
  P2.2 optimize counts: 1851 / 112 (6.05%), violating unchanged 1% mutation criterion.

## Root-cause observations

Read-only telemetry (no scheduler mutations) in
https://github.com/159357yangjun/SwarmBalance/actions/runs/38036706534:

| Test face | Blocked drone-steps | Different blocked drones | flush_size | flush_emergency | flush_timeout | optimize |
|---|---:|---:|---:|---:|---:|---:|
| gate (6 drones, 240 tasks) | 2570 | 2 | 1 | 1388 | 462 | 1851 |
| mutate (10 drones, 240 tasks) | 3634 | 2 | 0 | 69 | 43 | 112 |
| noDenom (10 drones, 60 tasks) | 0 | 0 | 0 | 0 | 0 | 0 |

In the P2.2 version, fail-closed flight-energy blocking changes the real fleet's
availability and consequently PSO emergency/timeout flushes. Total optimize
calls now combine fleet-load sensitivity and battery-depletion consequences.
The original test was designed for the former, not the latter.

## Minimal fixture correction

Only **disposable G2 speed-fallback test configurations** are scaled: original
battery capacities are multiplied by 20 via `console/g2_speed_fixture.py`.
The production config, actual battery-consumption formula, motion safety gate,
PSO algorithm, threshold 15, and original strict mutation assertion
`m_opt * 100 < g_opt` are unchanged.

The G2 full-flight probes now additionally **fail** if any real P2.2 flight
gate is activated, instead of silently interpreting blocked flights as a
speed/denominator fixture signal. All three fleet faces use the same energy
budget; the sole mutant remains the fleet size (mix 6 versus 10).

The counterfactual passed with real P2.2 `Drone.update()` and `Environment.step()`
in https://github.com/159357yangjun/SwarmBalance/actions/runs/38036789460:
gate optimize=1306, mutate=0, noDenom=0, blocked steps=0 in all faces;
the unchanged <1% test criterion holds.

## Repair verification and limits

- Narrow G2 + L1 calibration + P2.2 contract suite:
  https://github.com/159357yangjun/SwarmBalance/actions/runs/38036999255
  — **42 actual tests, all pass**, including real safety checks.
- This high-capacity speed-input fixture **does not** provide physically
  plausible flight endurance, nor evidence for actual energy consumption,
  mission recovery, dispatch quality or battery failure rates.
- Real low-battery behavior remains covered by P2.1/P2.2 and the forced
  P2.3b experiments, with original production battery capacities.
- Keep E0/E1 archives immutable, B default unchanged, all PRs unmerged.
- Full grouped `console / frontend / experiments / root` CI must be
  verified from its own run; narrow CI success is not full-suite success.
