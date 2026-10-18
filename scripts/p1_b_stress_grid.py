# -*- coding: utf-8 -*-
"""P1-B frozen-arrival, paired energy-accounting experiment (not a model patch).

Commands:
 calibrate: 3 candidate arrival profiles x 10 seeds; reject a capped/flat gradient.
 pair: replay the SAME exogenous task tape, in two isolated subprocesses for each seed.
 aggregate: check all 30 pairs, write auditable CSV, JSON and Markdown.
No file under results/ or frozen E0/E1 is written. All outputs live at --outdir.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

PROFILES = {"normal": 1.0, "elevated": 0.65, "high": 0.4}
SEEDS = tuple(range(51001, 51011))
HORIZON = 3600
TASK_CAP = 500
SOURCE_SHA = "7c5cc2745ae380278ef75c71271bb530e653d87e"
METRICS = ("completion_rate", "timeout_rate_completed_only", "avg_delay_s",
           "empty_ratio", "energy_wh", "swap_sessions", "unfinished")


def canonical(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint(data):
    return hashlib.sha256(canonical(data).encode("utf-8")).hexdigest()


def put(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)
                    + "\n", encoding="utf-8")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def prepare(root, profile, outdir):
    if profile not in PROFILES:
        raise ValueError("unknown profile: " + profile)
    original = read(root / "config" / "simulation.json")
    cfg = copy.deepcopy(original)
    cfg["environment"]["episode_max_steps"] = HORIZON
    cfg["task_generation"]["mode"] = "realistic"
    cfg["task_generation"]["realistic"]["total_tasks"] = TASK_CAP
    cfg["task_generation"]["realistic"]["interval_scale"] = PROFILES[profile]
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    file = outdir / ("scenario-" + profile + ".json")
    put(file, cfg)
    meta = {
        "profile": profile, "interval_scale": PROFILES[profile],
        "episode_seconds": HORIZON, "task_cap": TASK_CAP,
        "num_drones": cfg["environment"]["num_drones"],
        "fleet_mix": cfg["heterogeneous"]["fleet_mix"],
        "config_sha256": fingerprint(cfg),
        "original_config_sha256": fingerprint(original),
        "map": "frontend/data/map/part_of_yangpu.osm",
        "task_tape_semantics": "exogenous realistic generator; no dispatch during tape construction",
    }
    return file.resolve(), meta


def install(root, config):
    os.chdir(root)
    sys.path.insert(0, str(root / "frontend"))
    sys.path.insert(0, str(root))
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(config)


def task_row(task):
    return {
        "task_id": task.task_id, "weight": task.weight, "volume": task.volume,
        "category": task.category, "priority": task.priority,
        "deadline": task.deadline, "generation_time": task.generation_time,
        "source": list(task.get_source()),
        "destination": list(task.get_destination()),
    }


def make_tape(root, config, seed):
    install(root, config)
    from seed_interface import apply_seed
    from task import TaskGenerator
    apply_seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):
        gen = TaskGenerator()
        gen.reset()
        gen.set_seed(seed)
        tape = [task_row(t) for t in gen.generate_initial_tasks(0)]
        for step in range(1, HORIZON + 1):
            tape.extend(task_row(t) for t in gen.step(step))
    if not tape:
        raise AssertionError("[STRESS_EMPTY_TAPE] generator created nothing")
    if len(tape) >= TASK_CAP or gen.is_exhausted:
        raise AssertionError("[STRESS_HIDDEN_CAP] task cap hit: %s" % len(tape))
    if any(row["generation_time"] is None for row in tape):
        raise AssertionError("missing generation time")
    if any(float(row["generation_time"]) > HORIZON for row in tape):
        raise AssertionError("generated task past horizon")
    return tape


class FrozenTaskSource:
    """Only task-stream interface; no change to Environment/Greedy/Drone."""

    def __init__(self, records):
        self.records = list(records)
        self.cursor = 0
        self.unassigned_tasks = []
        self.total_tasks_generated = 0

    @property
    def is_exhausted(self):
        return self.cursor >= len(self.records)

    def reset(self):
        self.cursor = 0
        self.unassigned_tasks = []
        self.total_tasks_generated = 0

    def set_seed(self, seed):
        pass  # The entire task tape is already frozen and independently hashed.

    def _issue(self, now):
        from task import Task
        issued = []
        while self.cursor < len(self.records):
            row = self.records[self.cursor]
            at = float(row["generation_time"])
            if at > now:
                break
            if at < now:
                raise AssertionError("[STRESS_TAPE_LATE] missed task at %.1f" % at)
            issued.append(Task(
                task_id=row["task_id"], weight=row["weight"],
                source=tuple(row["source"]), destination=tuple(row["destination"]),
                deadline=row["deadline"], priority=row["priority"],
                generation_time=row["generation_time"],
                volume=row["volume"], category=row["category"],
            ))
            self.cursor += 1
        self.unassigned_tasks.extend(issued)
        self.total_tasks_generated += len(issued)
        return issued

    def generate_initial_tasks(self, current_time=0):
        return self._issue(current_time)

    def step(self, current_time):
        return self._issue(current_time)


def simulate(root, config, tape, mode, seed, profile, output):
    if mode not in ("assigned", "onboard"):
        raise ValueError("unrecognized mode")
    install(root, config)
    os.environ["SWARM_BALANCE_ENERGY_ACCOUNTING"] = mode
    from environment import Environment
    from greedy.scheduler import greedy_action_from_observation

    records = read(tape)["tasks"]
    tape_hash = fingerprint(records)
    osm = root / "frontend" / "data" / "map" / "part_of_yangpu.osm"
    if not osm.is_file():
        raise FileNotFoundError(osm)
    with contextlib.redirect_stdout(io.StringIO()):
        env = Environment(str(osm), episode_max_steps=HORIZON)
        env.task_generator = FrozenTaskSource(records)
        obs = env.reset(seed=seed)
        done = False
        max_waiting = len(env.task_generator.unassigned_tasks)
        while not done:
            action = greedy_action_from_observation(obs)
            obs, _, done, _ = env.step(action)
            max_waiting = max(max_waiting, len(env.task_generator.unassigned_tasks))
        stats = env.get_statistics()
    generated = int(env.total_generated_tasks)
    completed = int(env.total_completed_tasks)
    if generated != len(records):
        raise AssertionError("[STRESS_TAPE_COUNT] generated=%d tape=%d" % (generated, len(records)))
    if len(env.generated_task_times) != generated:
        raise AssertionError("[STRESS_GENERATION_LEDGER] missing generation times")
    dist = float(env.total_flight_distance)
    empty = float(env.total_empty_distance)
    loaded = float(env.total_loaded_distance)
    if not math.isclose(dist, empty + loaded, abs_tol=1e-5):
        raise AssertionError("[STRESS_MILEAGE] distance conservation violation")
    if completed > generated:
        raise AssertionError("[STRESS_COMPLETED_OVER_GENERATED]")
    row = {
        "profile": profile, "seed": seed, "mode": mode,
        "steps": float(env.current_time), "generated": generated,
        "completed": completed, "unfinished": generated-completed,
        "max_waiting": max_waiting,
        "completion_rate": completed / generated,
        "timeout_rate_completed_only": float(stats["timeout_rate"]),
        "avg_delay_s": float(stats["avg_delay"]),
        "empty_ratio": empty / dist if dist else 0.0,
        "distance_m": dist, "empty_m": empty, "loaded_m": loaded,
        "energy_wh": float(env.total_energy_consumed),
        "swap_sessions": int(env.total_swap_sessions),
        "tape_sha256": tape_hash,
        "config_sha256": fingerprint(read(config)),
    }
    for k in METRICS:
        if not math.isfinite(float(row[k])):
            raise AssertionError("nonfinite KPI " + k)
    put(output, row)
    print("[STRESS_SIM] " + canonical(row), flush=True)


def do_calibrate(args):
    root, out = Path(args.root).resolve(), Path(args.outdir).resolve()
    result = {"seeds": list(SEEDS), "profiles": {}, "source_sha": SOURCE_SHA,
              "purpose": "arrival-pressure calibration; no delivery/KPI inference"}
    for profile in PROFILES:
        cfg, meta = prepare(root, profile, out / "configs")
        # The config is read by module globals at import time. Run each
        # profile in an isolated interpreter, never hot-reload a cached CFG.
        counts_path = out / "calibration-counts" / (profile + ".json")
        env = os.environ.copy()
        env["SWARM_BALANCE_SIM_CONFIG"] = str(cfg)
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "count",
                        "--root", str(root), "--config", str(cfg),
                        "--output", str(counts_path)],
                       env=env, cwd=root, check=True)
        counts = read(counts_path)["counts"]
        if len(counts) != len(SEEDS):
            raise AssertionError("[STRESS_CALIBRATION_INCOMPLETE]")
        result["profiles"][profile] = {**meta, "generated_per_seed": counts,
                                        "generated_mean": statistics.mean(counts)}
        print("[STRESS_CALIBRATION] %s" %
              canonical(result["profiles"][profile]), flush=True)
    p = result["profiles"]
    n, m, h = [p[k]["generated_mean"] for k in PROFILES]
    put(out / "calibration.json", result)
    if not (n * 1.15 < m and m * 1.15 < h):
        raise AssertionError("[STRESS_NOT_SEPARATED] mean arrivals %.2f %.2f %.2f" %
                             (n, m, h))
    if any(max(p[k]["generated_per_seed"]) >= TASK_CAP for k in PROFILES):
        raise AssertionError("[STRESS_CAP_HIT]")
    print("[STRESS_CALIBRATION_PASS] arrivals %.2f < %.2f < %.2f cap=%d" %
          (n, m, h, TASK_CAP), flush=True)


def do_pair(args):
    root, out = Path(args.root).resolve(), Path(args.outdir).resolve()
    profile = args.profile
    if profile not in PROFILES or args.shard not in (0, 1):
        raise ValueError("invalid scenario/shard")
    calibration = read(args.calibration)
    cfg, meta = prepare(root, profile, out / "configs")
    if meta["config_sha256"] != calibration["profiles"][profile]["config_sha256"]:
        raise AssertionError("[STRESS_CONFIG_DRIFT] scenario content differs from gate")
    seeds = SEEDS[args.shard * 5:(args.shard + 1) * 5]
    for seed in seeds:
        tape = make_tape(root, cfg, seed)
        index = SEEDS.index(seed)
        if len(tape) != calibration["profiles"][profile]["generated_per_seed"][index]:
            raise AssertionError("[STRESS_TAPE_DRIFT] seed=%d" % seed)
        tape_file = out / "tapes" / ("tape-%s-%d.json" % (profile, seed))
        put(tape_file, {"seed": seed, "profile": profile, "tasks": tape,
                        "tape_sha256": fingerprint(tape)})
        rows = []
        for mode in ("assigned", "onboard"):
            output = out / "runs" / ("%s-%d-%s.json" % (profile, seed, mode))
            env = os.environ.copy()
            env["SWARM_BALANCE_SIM_CONFIG"] = str(cfg)
            env["SWARM_BALANCE_ENERGY_ACCOUNTING"] = mode
            cmd = [sys.executable, str(Path(__file__).resolve()), "simulate",
                   "--root", str(root), "--config", str(cfg), "--tape", str(tape_file),
                   "--profile", profile, "--seed", str(seed), "--mode", mode,
                   "--output", str(output)]
            subprocess.run(cmd, env=env, cwd=root, check=True)
            rows.append(read(output))
        a, b = rows
        for key in ("generated", "tape_sha256", "config_sha256", "seed", "profile"):
            if a[key] != b[key]:
                raise AssertionError("[STRESS_PAIR_NOT_COMPARABLE] %s" % key)
        pair = {"profile": profile, "seed": seed, "control": a,
                "experiment": b, "delta": {k: b[k]-a[k] for k in METRICS},
                "frozen_task_tape_sha256": a["tape_sha256"],
                "config_sha256": a["config_sha256"],
                "source_sha": args.source_sha}
        put(out / "pairs" / ("pair-%s-%d.json" % (profile, seed)), pair)
        print("[STRESS_PAIR] " + canonical({
            "profile": profile, "seed": seed, "generated": a["generated"],
            "assigned_energy_wh": a["energy_wh"], "onboard_energy_wh": b["energy_wh"],
            "completion_delta": pair["delta"]["completion_rate"],
            "delay_delta_s": pair["delta"]["avg_delay_s"],
            "energy_delta_wh": pair["delta"]["energy_wh"],
            "swap_delta": pair["delta"]["swap_sessions"],
        }), flush=True)


def do_aggregate(args):
    out = Path(args.outdir).resolve()
    files = list(out.rglob("pair-*.json"))
    pairs = [read(x) for x in files]
    seen = [(r["profile"], r["seed"]) for r in pairs]
    expected = [(p, s) for p in PROFILES for s in SEEDS]
    if len(pairs) != len(expected) or set(seen) != set(expected):
        raise AssertionError("[STRESS_GRID_INCOMPLETE] found=%d unique=%d expected=%d" %
                             (len(pairs), len(set(seen)), len(expected)))
    pairs.sort(key=lambda r: (list(PROFILES).index(r["profile"]), r["seed"]))
    if any(row["source_sha"] != args.source_sha for row in pairs):
        raise AssertionError("[STRESS_SHA_DRIFT]")
    cols = ["profile", "seed", "mode", "generated", "completed", "unfinished",
            "completion_rate", "timeout_rate_completed_only", "avg_delay_s",
            "empty_ratio", "energy_wh", "swap_sessions", "max_waiting",
            "distance_m", "tape_sha256", "config_sha256"]
    with (out / "all_runs.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for pair in pairs:
            for key in ("control", "experiment"):
                writer.writerow({k: pair[key].get(k) for k in cols})
    rows = []
    for profile in PROFILES:
        items = [p for p in pairs if p["profile"] == profile]
        data = {"profile": profile, "seeds": list(SEEDS)}
        for k in METRICS:
            a = [x["control"][k] for x in items]
            b = [x["experiment"][k] for x in items]
            d = [x["delta"][k] for x in items]
            data[k] = {"assigned_mean": statistics.mean(a),
                       "onboard_mean": statistics.mean(b),
                       "delta_mean": statistics.mean(d),
                       "delta_sd": statistics.stdev(d),
                       "delta_min": min(d), "delta_max": max(d)}
        rows.append(data)
        print("[STRESS_AGG] " + canonical(data), flush=True)
    summary = {"source_sha": args.source_sha, "calibration": read(args.calibration),
               "count_pairs": len(pairs), "count_episodes": 2 * len(pairs),
               "groups": rows,
               "warnings": [
                   "Exogenous tape is built with a realistic generator without dispatcher consumption.",
                   "timeout_rate_completed_only excludes unfinished tasks; do not call it full-demand lateness.",
                   "Ten seeds per profile are exploratory, not physical flight validation.",
                   "Old E0/E1 data and production energy formula are unchanged.",
               ]}
    put(out / "summary.json", summary)
    head = ["# P1-B paired pressure comparison", "",
            "Source SHA: `%s`" % args.source_sha,
            "30 frozen arrival tapes, 60 episodes, 10 paired seeds per profile.",
            "Three independent scenario configs are hashed in summary.json.",
            "",
            "| Profile | Generated (assigned mean) | Completion Δ | Delay Δ s | Empty ratio Δ | Energy Δ Wh | Swap Δ | Unfinished Δ |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        first = next(p for p in pairs if p["profile"] == row["profile"])
        head.append("| %s | %.2f | %+.5f | %+.3f | %+.5f | %+.2f | %+.2f | %+.2f |" %
                    (row["profile"], statistics.mean(
                        x["control"]["generated"] for x in pairs if x["profile"] == row["profile"]),
                     row["completion_rate"]["delta_mean"],
                     row["avg_delay_s"]["delta_mean"],
                     row["empty_ratio"]["delta_mean"],
                     row["energy_wh"]["delta_mean"],
                     row["swap_sessions"]["delta_mean"],
                     row["unfinished"]["delta_mean"]))
    head += ["", "Means of paired differences (onboard - assigned).",
             "See all_runs.csv, pair-*.json, tape-*.json and summary.json for witnesses.",
             "Historical E0/E1 is NOT overwritten; use only same scenario/config/tape for comparison.",
             "NOTE: output generated only upon successful completion of ALL jobs."]
    (out / "report.md").write_text("\n".join(head)+"\n", encoding="utf-8")
    print("[STRESS_REPORT_COMPLETE] paired=%d episodes=%d" %
          (len(pairs), len(pairs)*2), flush=True)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("calibrate", "count", "pair", "simulate", "aggregate"):
        q = sub.add_parser(name)
        q.add_argument("--root", default=".")
        q.add_argument("--outdir", default=".")
        q.add_argument("--source-sha", default=SOURCE_SHA)
        if name in ("pair", "simulate"):
            q.add_argument("--profile", required=True, choices=list(PROFILES))
            q.add_argument("--seed", type=int)
        if name == "pair":
            q.add_argument("--shard", required=True, type=int, choices=(0, 1))
            q.add_argument("--calibration", required=True)
        if name in ("simulate", "count"):
            q.add_argument("--config", required=True)
            q.add_argument("--output", required=True)
        if name == "simulate":
            q.add_argument("--tape", required=True)
            q.add_argument("--mode", required=True, choices=("assigned", "onboard"))
        if name == "aggregate":
            q.add_argument("--calibration", required=True)
    args = p.parse_args()
    if args.cmd == "calibrate":
        do_calibrate(args)
    elif args.cmd == "count":
        root = Path(args.root).resolve()
        cfg = Path(args.config).resolve()
        counts = [len(make_tape(root, cfg, seed)) for seed in SEEDS]
        put(args.output, {"seeds": list(SEEDS), "counts": counts})
        print("[STRESS_CALIBRATION_COUNTS] " + canonical(counts), flush=True)
    elif args.cmd == "pair":
        do_pair(args)
    elif args.cmd == "simulate":
        simulate(Path(args.root).resolve(), Path(args.config).resolve(), args.tape,
                 args.mode, args.seed, args.profile, args.output)
    else:
        do_aggregate(args)


if __name__ == "__main__":
    main()
