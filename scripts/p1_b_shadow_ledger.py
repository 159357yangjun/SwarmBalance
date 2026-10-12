# -*- coding: utf-8 -*-
"""P1.4 fixed-trajectory shadow *required* Wh for both cargo-mass conventions.

Runs the real Environment+Greedy without changing its battery or dispatch code.
Wraps Drone.consume_battery as a read-only witness: compute BOTH hypothetical
requirements on the same observed leg, then call original consume_battery once.
Does not simulate shadow battery state, swaps or route changes.
"""
from __future__ import annotations
import argparse
import contextlib
import csv
import gzip
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from collections import defaultdict

from p1_b_stress_grid import (HORIZON, PROFILES, SEEDS, FrozenTaskSource,
                              canonical, fingerprint, install, make_tape,
                              prepare, put, read)

BASELINE_SHA = "47c6e4582cd175151769ae8dd68383da805d3b3c"
P1_2_SHA = "f0f70f553dba76b54b02acc835561af1b8c4a25a"
ORIGINAL_EVIDENCE = "docs/evidence/P1_B_PAIRED_60_EPISODES.csv"
LEG_FIELDS = ("profile", "seed", "baseline", "step", "drone_id",
              "distance_m", "assigned_load_kg", "onboard_load_kg",
              "battery_before_wh", "base_wh_per_m", "penalty_factor",
              "wind_along_ms", "wind_multiplier", "assigned_required_wh",
              "onboard_required_wh", "active_required_wh",
              "active_debited_wh", "active_shortfall_wh",
              "battery_after_wh")


def expected_reference(root, profile, seed, mode):
    with (root / ORIGINAL_EVIDENCE).open(newline="", encoding="utf-8") as f:
        matches = [r for r in csv.DictReader(f)
                   if r["profile"] == profile and
                   int(r["seed"]) == seed and r["mode"] == mode]
    if len(matches) != 1:
        raise AssertionError("[SHADOW_BAD_REFERENCE] missing/duplicate source row")
    return matches[0]


def same(name, observed, expected):
    if not math.isclose(float(observed), float(expected), rel_tol=1e-10, abs_tol=1e-6):
        raise AssertionError("[SHADOW_TRAJECTORY_DRIFT] %s: %r vs %r" %
                             (name, observed, expected))


def simulate(root, cfg, tape_file, profile, seed, mode, out, sha):
    if mode not in ("assigned", "onboard"):
        raise ValueError("mode must be assigned/onboard")
    install(root, cfg)
    os.environ["SWARM_BALANCE_ENERGY_ACCOUNTING"] = mode
    from environment import Environment
    from greedy.scheduler import greedy_action_from_observation
    from drone import Drone

    expected = expected_reference(root, profile, seed, mode)
    tape = read(tape_file)
    records = tape["tasks"]
    tape_hash = fingerprint(records)
    config_hash = fingerprint(read(cfg))
    if expected["tape_sha256"] != tape_hash or expected["config_sha256"] != config_hash:
        raise AssertionError("[SHADOW_TAPE_CONFIG_DRIFT]")
    if tape.get("tape_sha256") != tape_hash:
        raise AssertionError("[SHADOW_TAPE_DIGEST]")

    rows = []
    totals = defaultdict(float)
    original = Drone.consume_battery
    active_key = "assigned_required_wh" if mode == "assigned" else "onboard_required_wh"
    env_ref = [None]

    def witness(drone, distance, wind_along=None):
        # Same mass and wind inputs that the real energy method observes,
        # captured before it changes the battery. This wrapper never changes
        # any drone state and invokes original exactly once.
        distance = float(distance)
        assigned = float(drone.current_load)
        onboard = float(drone.onboard_load_kg)
        capacity = float(drone.carrying_capacity)
        if not all(math.isfinite(x) for x in (distance, assigned, onboard, capacity)):
            raise AssertionError("[SHADOW_INVALID_MASS]")
        if distance < 0 or capacity <= 0 or not (0 <= assigned <= capacity) or not (0 <= onboard <= capacity):
            raise AssertionError("[SHADOW_LOAD_OUT_OF_RANGE]")
        wind_factor = drone._wind_factor(wind_along)
        base = distance * drone.battery_consumption_base * wind_factor
        required_assigned = base * (1 + assigned / capacity * drone.battery_load_penalty_factor)
        required_onboard = base * (1 + onboard / capacity * drone.battery_load_penalty_factor)
        if min(required_assigned, required_onboard) < 0:
            raise AssertionError("[SHADOW_NEGATIVE_REQUIREMENT]")
        battery_before = float(drone.current_battery)
        debited = original(drone, distance, wind_along)
        real_required = float(drone.last_energy_required_wh)
        real_shortfall = float(drone.last_energy_shortfall_wh)
        expected_active = required_assigned if mode == "assigned" else required_onboard
        same("leg active formula", real_required, expected_active)
        same("leg debit", debited, drone.last_energy_debited_wh)
        same("leg Wh ledger", real_required, debited + real_shortfall)
        same("leg battery conservation", battery_before - drone.current_battery, debited)
        step = float(env_ref[0].current_time)
        row = dict(profile=profile, seed=seed, baseline=mode, step=step,
                   drone_id=str(drone.drone_id), distance_m=distance,
                   assigned_load_kg=assigned, onboard_load_kg=onboard,
                   battery_before_wh=battery_before,
                   base_wh_per_m=float(drone.battery_consumption_base),
                   penalty_factor=float(drone.battery_load_penalty_factor),
                   wind_along_ms=wind_along, wind_multiplier=wind_factor,
                   assigned_required_wh=required_assigned,
                   onboard_required_wh=required_onboard,
                   active_required_wh=real_required, active_debited_wh=debited,
                   active_shortfall_wh=real_shortfall,
                   battery_after_wh=float(drone.current_battery))
        rows.append(row)
        totals["legs"] += 1
        totals["distance_m"] += distance
        for key in ("assigned_required_wh", "onboard_required_wh",
                    "active_required_wh", "active_debited_wh",
                    "active_shortfall_wh"):
            totals[key] += float(row[key])
        return debited

    from pathlib import Path
    osm = root / "frontend" / "data" / "map" / "part_of_yangpu.osm"
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            env = Environment(str(osm), episode_max_steps=HORIZON)
            env.task_generator = FrozenTaskSource(records)
            env_ref[0] = env
            Drone.consume_battery = witness
            obs = env.reset(seed=seed)
            done = False
            while not done:
                actions = greedy_action_from_observation(obs)
                obs, _, done, _ = env.step(actions)
            stats = env.get_statistics()
    finally:
        Drone.consume_battery = original

    if not rows:
        raise AssertionError("[SHADOW_NO_LEGS]")
    same("generated", env.total_generated_tasks, expected["generated"])
    same("completed", env.total_completed_tasks, expected["completed"])
    same("distance_m", env.total_flight_distance, expected["distance_m"])
    same("energy_wh", env.total_energy_consumed, expected["energy_wh"])
    same("swaps", env.total_swap_sessions, expected["swap_sessions"])
    same("completion_rate", stats["completion_rate"], expected["completion_rate"])
    same("avg_delay_s", stats["avg_delay"], expected["avg_delay_s"])
    same("empty_m", env.total_empty_distance, expected["empty_m"])
    same("loaded_m", env.total_loaded_distance, expected["loaded_m"])
    same("traveled distance", totals["distance_m"], env.total_flight_distance)
    same("active theoretical sum", totals["active_required_wh"],
         totals[active_key])
    same("sum required = debit + shortfall", totals["active_required_wh"],
         totals["active_debited_wh"] + totals["active_shortfall_wh"])

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    legs_path = out / ("legs-%s-%d-%s.csv.gz" % (profile, seed, mode))
    with gzip.open(legs_path, "wt", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LEG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    result = dict(profile=profile, seed=seed, baseline=mode,
                  source_sha=sha, baseline_evidence_sha=P1_2_SHA,
                  config_sha256=config_hash, tape_sha256=tape_hash,
                  **{k: float(v) for k,v in totals.items()},
                  shadow_formula_delta_wh=(totals["onboard_required_wh"] -
                                           totals["assigned_required_wh"]),
                  observed_energy_wh=float(env.total_energy_consumed),
                  observed_distance_m=float(env.total_flight_distance),
                  generated=int(env.total_generated_tasks),
                  completed=int(env.total_completed_tasks),
                  swaps=int(env.total_swap_sessions))
    put(out / ("shadow-%s-%d-%s.json" % (profile, seed, mode)), result)
    print("[SHADOW_LEGS] " + canonical({k:result[k] for k in
          ("profile","seed","baseline","legs","assigned_required_wh",
           "onboard_required_wh","shadow_formula_delta_wh",
           "active_required_wh","active_debited_wh","active_shortfall_wh")}),
          flush=True)


def shard(args):
    root=Path(args.root).resolve()
    out=Path(args.outdir).resolve()
    cfg,meta=prepare(root,args.profile,out/"configs")
    for seed in SEEDS[5*args.shard:5*(args.shard+1)]:
        # Different profile configs cannot be hot-reloaded across an interpreter.
        # CI runs exactly one profile per shard; each simulation is a subprocess.
        tape=make_tape(root,cfg,seed)
        tape_hash=fingerprint(tape)
        source=out/"tapes"/("tape-%s-%d.json"%(args.profile,seed))
        put(source,dict(profile=args.profile,seed=seed,tape_sha256=tape_hash,tasks=tape))
        for mode in ("assigned","onboard"):
            cmd=[sys.executable,str(Path(__file__).resolve()),"simulate",
                 "--root",str(root),"--config",str(cfg),"--tape",str(source),
                 "--profile",args.profile,"--seed",str(seed),"--mode",mode,
                 "--outdir",str(out),"--source-sha",args.source_sha]
            env=os.environ.copy()
            env["SWARM_BALANCE_SIM_CONFIG"]=str(cfg)
            env["SWARM_BALANCE_ENERGY_ACCOUNTING"]=mode
            subprocess.run(cmd,cwd=root,env=env,check=True)
    print("[SHADOW_SHARD_COMPLETE] %s shard=%d seeds=5 modes=2" %
          (args.profile,args.shard),flush=True)


def aggregate(args):
    out=Path(args.outdir).resolve()
    files=list(out.rglob("shadow-*.json"))
    rows=[read(f) for f in files]
    expected={(p,s,m) for p in PROFILES for s in SEEDS for m in ("assigned","onboard")}
    keyed={(r["profile"],r["seed"],r["baseline"]):r for r in rows}
    if len(rows)!=60 or set(keyed)!=expected:
        raise AssertionError("[SHADOW_INCOMPLETE] expected 60 actual %d unique %d"%
                             (len(rows),len(keyed)))
    pairs=[]
    for profile in PROFILES:
        for seed in SEEDS:
            a=keyed[profile,seed,"assigned"]
            b=keyed[profile,seed,"onboard"]
            if a["tape_sha256"]!=b["tape_sha256"] or a["config_sha256"]!=b["config_sha256"]:
                raise AssertionError("[SHADOW_PAIR_NOT_COMPARABLE]")
            for row in (a,b):
                if row["source_sha"] != args.source_sha or row["baseline_evidence_sha"]!=P1_2_SHA:
                    raise AssertionError("[SHADOW_SOURCE_SHA]")
                same("shadow sum",row["active_required_wh"],
                     row["active_debited_wh"]+row["active_shortfall_wh"])
                if row["legs"]<=0:
                    raise AssertionError("[SHADOW_ZERO_LEGS]")
            # Same baseline legs, alternate formula without changing battery,
            # then compare the two *different* observed trajectories.
            pairs.append(dict(profile=profile,seed=seed,
                              assigned_trajectory_shadow_delta_wh=a["shadow_formula_delta_wh"],
                              onboard_trajectory_shadow_delta_wh=b["shadow_formula_delta_wh"],
                              observed_debited_delta_wh=b["observed_energy_wh"]-a["observed_energy_wh"],
                              assigned_trajectory_m=a["observed_distance_m"],
                              onboard_trajectory_m=b["observed_distance_m"],
                              tape_sha256=a["tape_sha256"],config_sha256=a["config_sha256"]))
    groups=[]
    for profile in PROFILES:
        subset=[p for p in pairs if p["profile"]==profile]
        result=dict(profile=profile,n=len(subset))
        for key in ("assigned_trajectory_shadow_delta_wh",
                    "onboard_trajectory_shadow_delta_wh",
                    "observed_debited_delta_wh"):
            data=[r[key] for r in subset]
            result[key]={"mean":sum(data)/len(data),"min":min(data),"max":max(data),
                         "negative":sum(v<0 for v in data)}
        groups.append(result)
        print("[SHADOW_AGG] "+canonical(result),flush=True)
    evidence=dict(source_sha=args.source_sha,
                  p1_2_sha=P1_2_SHA,episodes=len(rows),pair_count=len(pairs),
                  source_kind="real Greedy trajectories + shadow required-Wh observation",
                  limits=[
                      "No shadow battery state is simulated; shortfall and swap behavior belong to the active baseline only.",
                      "Shadow difference is same-leg formula-required energy, not hypothetical delivered Wh after the alternate model changes routes.",
                      "The two active-baseline trajectories may differ. Cross-trajectory observed debit difference includes scheduling feedback.",
                      "The source P1.2 episodes are re-executed and checked against committed row-level distance/energy/completion/swaps.",
                  ],
                  profiles=groups,pairs=pairs)
    put(out/"P1_B_SHADOW_REPORT.json",evidence)
    with (out/"P1_B_SHADOW_PAIRS.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(pairs[0]))
        writer.writeheader()
        writer.writerows(pairs)
    report=["# P1.4 fixed-trajectory shadow required-energy audit","",
            "Original P1.2 inputs and seed-level activity cross-checked against prior 60 rows.",
            "All figures are theoretical required Wh evaluated on the SAME observed leg for each trajectory.",
            "These values are not shadow battery debit and do not model new swap schedules.","",
            "| Pressure | Assigned-run same-leg formula Δ Wh | Onboard-run same-leg formula Δ Wh | Cross-run actual debit Δ Wh |",
            "|---|---:|---:|---:|"]
    for g in groups:
        report.append("| %s | %.2f | %.2f | %.2f |"%(g["profile"],
                 g["assigned_trajectory_shadow_delta_wh"]["mean"],
                 g["onboard_trajectory_shadow_delta_wh"]["mean"],
                 g["observed_debited_delta_wh"]["mean"]))
    report += ["","Formula delta = on-board mass requirement minus assigned mass requirement evaluated at the identical captured instant, distance, wind and drone coefficients.",
               "Cross-run actual debit delta uses different baseline routes and battery trajectories; DO NOT treat the difference from either shadow figure as exact causal mediation.",
               "Full per-leg traces retained as compressed CSV artifacts. Historical E0/E1 not overwritten."]
    (out/"P1_B_SHADOW_REPORT.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    print("[SHADOW_COMPLETE] episodes=60 pairs=30 profiles=3",flush=True)


def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    for cmd in ("shard","simulate","aggregate"):
        s=sub.add_parser(cmd)
        s.add_argument("--root",default=".")
        s.add_argument("--outdir",default=".")
        s.add_argument("--source-sha",default=BASELINE_SHA)
        if cmd in ("shard","simulate"):
            s.add_argument("--profile",required=True,choices=tuple(PROFILES))
        if cmd=="shard":
            s.add_argument("--shard",type=int,required=True,choices=(0,1))
        if cmd=="simulate":
            s.add_argument("--seed",type=int,required=True)
            s.add_argument("--config",required=True)
            s.add_argument("--tape",required=True)
            s.add_argument("--mode",required=True,choices=("assigned","onboard"))
    a=p.parse_args()
    if a.command=="shard": shard(a)
    elif a.command=="simulate":
        simulate(Path(a.root).resolve(),Path(a.config).resolve(),a.tape,
                 a.profile,a.seed,a.mode,a.outdir,a.source_sha)
    else: aggregate(a)

if __name__=="__main__":
    main()
