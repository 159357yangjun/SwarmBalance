# -*- coding: utf-8 -*-
"""Independently re-check P1.3 aggregate against 60 raw GitHub job-log rows.

No third-party imports, no simulator execution, no state mutation.
Use --episodes and --summary (both committed evidence) as inputs.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

PROFILES = ("normal", "elevated", "high")
SEEDS = tuple(range(51001, 51011))
MODES = ("assigned", "onboard")
TCRIT_DF9 = 2.262157
METRICS = ("energy_delta_wh", "relative_energy_saving", "distance_delta_m",
           "distance_component_wh", "intensity_component_wh", "intensity_delta_wh_m",
           "completion_delta", "avg_delay_delta_s", "unfinished_delta", "swaps_delta",
           "timeout_completed_delta", "empty_ratio_delta")


def check(condition, text):
    if not condition:
        raise AssertionError("[P1_3_EVIDENCE_FAILURE] " + text)


def numeric(row):
    x = dict(row)
    for key in ("seed", "generated", "completed", "unfinished", "swap_sessions",
                "max_waiting"):
        x[key] = int(x[key])
    for key in ("completion_rate", "timeout_rate_completed_only", "avg_delay_s",
                "energy_wh", "distance_m", "empty_m", "loaded_m", "empty_ratio"):
        x[key] = float(x[key])
        check(math.isfinite(x[key]), "nonfinite " + key)
    return x


def describe(values):
    check(len(values) == 10, "require exactly 10 samples")
    m = statistics.mean(values)
    sd = statistics.stdev(values)
    radius = TCRIT_DF9 * sd / math.sqrt(10)
    return dict(mean=m, sd=sd, ci95_low=m-radius, ci95_high=m+radius,
                min=min(values), max=max(values),
                better=sum(v > 1e-10 for v in values),
                worse=sum(v < -1e-10 for v in values),
                zero=sum(abs(v) <= 1e-10 for v in values))


def analyze(rows):
    check(len(rows) == 60, "must see 60 real simulator rows")
    indexed = {(x["profile"], x["seed"], x["mode"]): x for x in rows}
    check(len(indexed) == 60, "duplicates present")
    keys = {(p, s, m) for p in PROFILES for s in SEEDS for m in MODES}
    check(set(indexed) == keys, "missing or extra profile/seed/mode")
    grouped = {}
    regressions = 0
    for profile in PROFILES:
        paired = []
        for seed in SEEDS:
            a = indexed[profile, seed, "assigned"]
            b = indexed[profile, seed, "onboard"]
            check(a["generated"] == b["generated"], "different order counts")
            check(a["tape_sha256"] == b["tape_sha256"], "different task tape")
            check(a["config_sha256"] == b["config_sha256"], "different scenario config")
            check(a["generated"] >= a["completed"] and b["generated"] >= b["completed"],
                  "completion exceeds generation")
            for item in (a, b):
                check(abs(item["distance_m"] - item["empty_m"] - item["loaded_m"]) < 1e-4,
                      "distance ledger does not conserve")
                check(item["generated"] - item["completed"] == item["unfinished"],
                      "unfinished accounting mismatch")
            ai, bi = (a["energy_wh"]/a["distance_m"],
                      b["energy_wh"]/b["distance_m"])
            dist_component = (b["distance_m"]-a["distance_m"])*ai
            intensity_component = b["distance_m"]*(bi-ai)
            energy_delta = b["energy_wh"]-a["energy_wh"]
            check(abs(energy_delta-dist_component-intensity_component)<1e-7,
                  "energy decomposition identity failed")
            check(energy_delta < 0, "claimed universal 30/30 energy reduction violated")
            completion_delta = b["completion_rate"]-a["completion_rate"]
            regressions += completion_delta < -1e-10
            paired.append(dict(
                energy_delta_wh=energy_delta,
                relative_energy_saving=(a["energy_wh"]-b["energy_wh"])/a["energy_wh"],
                distance_delta_m=b["distance_m"]-a["distance_m"],
                distance_component_wh=dist_component,
                intensity_component_wh=intensity_component,
                intensity_delta_wh_m=bi-ai,
                completion_delta=completion_delta,
                avg_delay_delta_s=b["avg_delay_s"]-a["avg_delay_s"],
                unfinished_delta=b["unfinished"]-a["unfinished"],
                swaps_delta=b["swap_sessions"]-a["swap_sessions"],
                timeout_completed_delta=b["timeout_rate_completed_only"]-
                                        a["timeout_rate_completed_only"],
                empty_ratio_delta=b["empty_ratio"]-a["empty_ratio"],
            ))
        grouped[profile] = {"n": len(paired), "metrics":
                            {key: describe([p[key] for p in paired]) for key in METRICS}}
    check(regressions == 11, "completion regression count differs from actual job logs")
    return grouped, regressions


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--episodes", default="docs/evidence/P1_B_PAIRED_60_EPISODES.csv")
    p.add_argument("--summary", default="docs/evidence/P1_B_PAIRED_30_SEED_STATS.json")
    args = p.parse_args()
    with Path(args.episodes).open(newline="", encoding="utf-8") as f:
        rows = [numeric(x) for x in csv.DictReader(f)]
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    check(summary["evidence"]["run_id"] == 38021072705, "wrong GitHub evidence run")
    check(summary["evidence"]["source_commit"] ==
          "f0f70f553dba76b54b02acc835561af1b8c4a25a", "wrong simulation source SHA")
    grouped, regressions = analyze(rows)
    for profile in PROFILES:
        check(summary["profiles"][profile]["n"] == 10, "wrong sample count")
        for metric in METRICS:
            for field, observed in grouped[profile]["metrics"][metric].items():
                claimed = summary["profiles"][profile]["metrics"][metric][field]
                if isinstance(observed, int):
                    check(observed == claimed, profile + " " + metric + " " + field)
                else:
                    check(math.isclose(observed, claimed, rel_tol=1e-9, abs_tol=1e-8),
                          profile + " " + metric + " " + field)
        print("[P1_3_POSTHOC] %s paired=10 relative_saving_mean=%.8f "
              "energy_delta_mean_wh=%.4f regressions=%d" % (
                  profile, grouped[profile]["metrics"]["relative_energy_saving"]["mean"],
                  grouped[profile]["metrics"]["energy_delta_wh"]["mean"],
                  grouped[profile]["metrics"]["completion_delta"]["worse"]), flush=True)
    print("[P1_3_POSTHOC_PASS] episodes=60 pairs=30 energy_reductions=30 "
          "completion_regressions=%d valid_distance_intensity_identity=30" %
          regressions, flush=True)


if __name__ == "__main__":
    main()
