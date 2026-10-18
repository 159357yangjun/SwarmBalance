# -*- coding: utf-8 -*-
"""P1 paired real-simulation readout; never writes project results/ artifacts.

Run this SAME script in separate Python processes against the old Git worktree
and the PR candidate, using identical seeds and real greedy actions.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import sys
from pathlib import Path


def simulate(root: Path, seed: int, steps: int):
    # Must be a fresh subprocess for each code revision. Config and imports are
    # frozen at module import time, so reloading them in one process is invalid.
    os.chdir(root)
    sys.path[:0] = [str(root / "frontend"), str(root)]
    from environment import Environment
    from greedy.scheduler import greedy_action_from_observation

    osm = root / "frontend" / "data" / "map" / "part_of_yangpu.osm"
    if not osm.is_file():
        raise FileNotFoundError(str(osm))
    with contextlib.redirect_stdout(io.StringIO()):
        env = Environment(str(osm), episode_max_steps=steps)
        observation = env.reset(seed=seed)
        done = False
        while not done:
            action = greedy_action_from_observation(observation)
            observation, _, done, _ = env.step(action)
        stats = env.get_statistics()
    distance = float(env.total_flight_distance)
    empty = float(env.total_empty_distance)
    loaded = float(env.total_loaded_distance)
    if not math.isclose(distance, empty + loaded, abs_tol=1e-5):
        raise AssertionError("[P1_SEEDED_MILEAGE] total != empty + loaded")
    return {
        "seed": seed,
        "steps": int(env.current_time),
        "generated": int(env.total_generated_tasks),
        "completed": int(env.total_completed_tasks),
        "completion_rate": float(stats.get("completion_rate", 0.0)),
        "avg_delay_s": float(stats.get("avg_delay", 0.0)),
        "empty_ratio": empty / distance if distance > 0 else 0.0,
        "empty_distance_m": empty,
        "loaded_distance_m": loaded,
        "total_distance_m": distance,
        "energy_wh": float(env.total_energy_consumed),
        "swap_sessions": int(env.total_swap_sessions),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--seeds", default="40901,40902")
    p.add_argument("--steps", type=int, default=900)
    p.add_argument("--label", default="candidate")
    p.add_argument("--output")
    p.add_argument("--compare", nargs=2, metavar=("BEFORE_JSON", "AFTER_JSON"))
    args = p.parse_args()

    if args.compare:
        before, after = [json.loads(Path(f).read_text(encoding="utf-8"))
                         for f in args.compare]
        bs = {x["seed"]: x for x in before["rows"]}
        as_ = {x["seed"]: x for x in after["rows"]}
        if set(bs) != set(as_):
            raise AssertionError("seed pairing changed")
        keys = ("completion_rate", "avg_delay_s", "empty_ratio",
                "energy_wh", "swap_sessions")
        for seed in sorted(bs):
            b, a = bs[seed], as_[seed]
            changes = {k: {"before": b[k], "after": a[k], "delta": a[k] - b[k]}
                       for k in keys}
            print("[P1_PAIRED] seed=%d %s" %
                  (seed, json.dumps(changes, sort_keys=True, ensure_ascii=False)), flush=True)
        for k in keys:
            bv = sum(bs[s][k] for s in bs) / len(bs)
            av = sum(as_[s][k] for s in as_) / len(as_)
            print("[P1_PAIRED_MEAN] metric=%s before=%.8f after=%.8f delta=%+.8f" %
                  (k, bv, av, av - bv), flush=True)
        return

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    if not seeds or args.steps <= 0 or len(set(seeds)) != len(seeds):
        raise ValueError("invalid seed/steps selection")
    root = Path(args.root).resolve()
    rows = []
    for seed in seeds:
        row = simulate(root, seed, args.steps)
        if any(not math.isfinite(row[k]) for k in
               ("completion_rate", "avg_delay_s", "empty_ratio", "energy_wh")):
            raise AssertionError("non-finite simulated KPI")
        rows.append(row)
        print("[P1_SEEDED] label=%s %s" %
              (args.label, json.dumps(row, sort_keys=True, ensure_ascii=False)), flush=True)
    output = {"revision": args.label, "root": str(root), "rows": rows}
    if args.output:
        Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print("[P1_SEEDED_FINISH] label=%s seeds=%s steps=%d" %
          (args.label, seeds, args.steps), flush=True)


if __name__ == "__main__":
    main()
