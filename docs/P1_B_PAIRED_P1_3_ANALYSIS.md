# P1.3 | B energy accounting: seed-paired uncertainty and mileage/intensity breakdown

**Status:** retrospective statistical review of existing P1.1/P1.2 Actions evidence; **no new simulation runs**.

**Verified evidence:** [Actions #38021072705](https://github.com/159357yangjun/SwarmBalance/actions/runs/38021072705) (`completed/success`), original code SHA `f0f70f553dba76b54b02acc835561af1b8c4a25a`. Six original jobs: 114122128022, 114122128025, 114122128027, 114122128049, 114122128050, 114122128139. All **60** `[STRESS_SIM]` rows collected from those six jobs; **30** unique `(profile, seed)` pairs with identical task tape SHA, scenario config SHA and generated demand within each pair.

### Mean differences (B onboard minus A+C assigned)

| Profile | Mean Δenergy Wh (95% CI) | Mean per-seed saving % (95% CI) | Mean Δcompletion pp (95% CI) | Mean Δdelay s (95% CI) | Completion regressions |
|---|---:|---:|---:|---:|---:|
| normal | -1672.5 [-2048.5, -1296.6] | 6.10 [4.74, 7.46] | -0.004 [-0.590, 0.582] | -0.79 [-2.44, 0.87] | 3/10 |
| elevated | -1922.1 [-2427.0, -1417.1] | 5.27 [3.93, 6.61] | 0.250 [-0.528, 1.028] | -2.67 [-6.74, 1.39] | 3/10 |
| high | -2057.9 [-2366.3, -1749.6] | 5.15 [4.39, 5.90] | 0.331 [-1.014, 1.676] | -3.45 [-17.62, 10.71] | 5/10 |

**Main pattern:** energy is lower in all 30 paired seeds. In contrast, 11/30 paired seeds lose completion rate (3 normal, 3 elevated, 5 high); all three paired completion-rate confidence intervals include zero. The intervals do **not** establish non-inferiority. In 10-seed groups, confidence intervals are exploratory and multiple metrics have not been multiplicity-adjusted.

### Exact energy difference accounting identity, not a causal formula estimate

Per pair, use actual debited simulated energy `E`, actual simulated distance `D`, mean debited energy intensity `I=E/D`. The exact identity is:

`E_B - E_A = (D_B - D_A) * I_A + D_B * (I_B - I_A)`.

The first term is a **distance-accounting component**. The second is an **observed energy-intensity component**. It includes route composition, fleet activity, cargo and charging-state feedback as well as the changed billing formula. It is **not** an isolation of the formula's causal effect on identical trajectories.

| Profile | Mean Δdistance km (95% CI) | Mean distance component Wh | Mean observed intensity component Wh | Net Δenergy Wh |
|---|---:|---:|---:|---:|
| normal | 1.33 [-2.56, 5.21] | 123.5 | -1796.1 | -1672.5 |
| elevated | 0.42 [-7.20, 8.04] | 36.7 | -1958.8 | -1922.1 |
| high | 3.98 [0.15, 7.82] | 311.2 | -2369.1 | -2057.9 |

The mean distance component is **positive** in all three groups, meaning the net savings cannot be attributed to consistently shorter total flight. The high-pressure group flew approximately 3.98 km more per episode on average, while energy still fell. These algebraic components sum to the net energy change by construction (per-pair residual < 1e-7 Wh).

### Completion regression audit (all affected seeds)

| Profile | Seed | Completion Δ (percentage points) | Energy Δ (Wh) | Delay Δ (seconds) |
|---|---:|---:|---:|---:|
| normal | 51003 | -1.031 | -619.2 | -3.48 |
| normal | 51005 | -0.990 | -1333.2 | -3.64 |
| normal | 51010 | -1.010 | -1674.9 | 4.46 |
| elevated | 51003 | -0.645 | -2175.9 | 6.96 |
| elevated | 51005 | -1.935 | -3153.1 | -0.98 |
| elevated | 51008 | -0.617 | -463.0 | 1.57 |
| high | 51001 | -1.633 | -1852.3 | -1.30 |
| high | 51002 | -1.224 | -1988.0 | -27.48 |
| high | 51004 | -0.820 | -2182.6 | 26.04 |
| high | 51008 | -2.449 | -2340.7 | -7.12 |
| high | 51009 | -0.410 | -2624.3 | -37.99 |

### Measurement and policy limits

- The generator is frozen before simulation, and the same tape is used for both modes. This controls order arrivals but not post-arrival dispatch decisions and flight traces.
- This study cannot assign a specific portion of savings **causally** to the onboard load formula. An identical-trajectory shadow-accounting replay or ablation with frozen dispatch actions and leg-level Wh is needed for that separate claim.
- The total-energy metric uses **actual debits**, not necessarily theoretical required energy under battery shortages. Existing P1-C contracts separate required, debit and shortfall; further causal work should collect those leg-level components.
- The reported timeout fraction is **conditional on completed tasks**, not a deadline failure rate over generated demand. See also the nonzero unfinished task counts.
- Confidence intervals use Student-t for ten seeds per profile and assume independent simulation seeds. They quantify simulation-seed variability, **not real drone physical uncertainty**, and are not proof of equivalence/no-harm.
- Input CSV is frozen in `docs/evidence/P1_B_PAIRED_60_EPISODES.csv`, extracted from first-hand job logs. Original per-task artifacts remain in GitHub Actions (30-day retention). No historical E0/E1 file was altered.

**Decision:** this is evidence of robust *simulated accounting energy reduction*; it is not yet evidence for changing the default production billing policy or claiming equivalence in service quality.
