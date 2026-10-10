# -*- coding: utf-8 -*-
"""P2.3: immutable P2.1 vs P2.2 code, same exogenous tasks, Greedy and seeds.

Simulator worktrees are actual Git commits, never a runtime disabled safety gate.
No production or frozen E0/E1 file is modified. Runs default assigned accounting.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import contextlib
import csv
import io
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
from p1_b_stress_grid import (PROFILES, SEEDS, HORIZON, FrozenTaskSource,
                              canonical, fingerprint, install, make_tape, prepare, put, read)

BEFORE="806d07653af52b83202ba232cb1f3e88dd9b7901"
AFTER="5bcc6cb9661dc250c11c578acbacc32c8b0d6f4f"
REF="docs/evidence/P1_B_PAIRED_60_EPISODES.csv"
METRICS=("completion_rate","unfinished","avg_delay_s","timeout_completed_only",
         "energy_wh","swap_sessions","distance_m","empty_ratio","max_queue",
         "unpaid_leg_events","unpaid_shortfall_wh","blocked_attempts",
         "blocked_drone_seconds","blocked_drone_count","blocked_at_end")


def gitsha(root):
    return subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()


def same(key,a,b):
    if not math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-6):
        raise AssertionError("[P2_3_REPLAY_DRIFT] %s: %r / %r"%(key,a,b))


def refrow(root,profile,seed):
    with (root/REF).open(newline="",encoding="utf-8") as f:
        rows=[x for x in csv.DictReader(f) if x["profile"]==profile
              and int(x["seed"])==seed and x["mode"]=="assigned"]
    if len(rows)!=1:
        raise AssertionError("[P2_3_REFERENCE_NOT_UNIQUE]")
    return rows[0]


def simulate(args):
    root=Path(args.root).resolve()
    version=args.version
    wanted={"before":BEFORE,"after":AFTER}[version]
    if gitsha(root)!=wanted:
        raise AssertionError("[P2_3_WRONG_CODE_COMMIT]")
    config=Path(args.config).resolve()
    install(root,config)
    os.environ["SWARM_BALANCE_ENERGY_ACCOUNTING"]="assigned"
    from environment import Environment
    from greedy.scheduler import greedy_action_from_observation
    from drone import Drone
    records=read(args.tape)["tasks"]
    tape_hash=fingerprint(records)
    config_hash=fingerprint(read(config))
    if tape_hash!=read(args.tape)["tape_sha256"]:
        raise AssertionError("[P2_3_BAD_TAPE_DIGEST]")
    original=refrow(Path(args.evidence_root).resolve(),args.profile,args.seed)
    if original["tape_sha256"]!=tape_hash or original["config_sha256"]!=config_hash:
        raise AssertionError("[P2_3_INPUT_DIFFERS_FROM_P1_2]")
    count=defaultdict(float)
    blocked_drones=set()
    blocked_step=set()
    prev_consume=Drone.consume_battery
    prev_gate=getattr(Drone,"_flight_step_feasible",None)

    def tracked_consume(drone,distance,wind_along=None):
        used=prev_consume(drone,distance,wind_along)
        if distance>0 and drone.last_energy_shortfall_wh>1e-9:
            count["unpaid_leg_events"]+=1
            count["unpaid_shortfall_wh"]+=drone.last_energy_shortfall_wh
        return used

    def tracked_gate(drone,distance,wind_along):
        ok=prev_gate(drone,distance,wind_along)
        if not ok:
            count["blocked_attempts"]+=1
            blocked_drones.add(str(drone.drone_id))
            blocked_step.add(str(drone.drone_id))
        return ok

    Drone.consume_battery=tracked_consume
    if version=="after":
        if prev_gate is None:
            raise AssertionError("[P2_3_MISSING_SAFETY_GATE]")
        Drone._flight_step_feasible=tracked_gate
    elif prev_gate is not None:
        raise AssertionError("[P2_3_LEGACY_HAS_GATE]")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            osm=root/"frontend"/"data"/"map"/"part_of_yangpu.osm"
            env=Environment(str(osm),episode_max_steps=HORIZON)
            env.task_generator=FrozenTaskSource(records)
            obs=env.reset(seed=args.seed)
            done=False
            maxqueue=len(env.task_generator.unassigned_tasks)
            while not done:
                blocked_step.clear()
                action=greedy_action_from_observation(obs)
                obs,_,done,_=env.step(action)
                count["blocked_drone_seconds"]+=len(blocked_step)
                maxqueue=max(maxqueue,len(env.task_generator.unassigned_tasks))
            stats=env.get_statistics()
    finally:
        Drone.consume_battery=prev_consume
        if version=="after":
            Drone._flight_step_feasible=prev_gate

    generated=int(env.total_generated_tasks)
    completed=int(env.total_completed_tasks)
    if generated!=len(records) or len(env.generated_task_times)!=generated:
        raise AssertionError("[P2_3_GENERATED_TAPE_MISMATCH]")
    dist=float(env.total_flight_distance)
    same("distance ledger",dist,float(env.total_empty_distance)+float(env.total_loaded_distance))
    if version=="before":
        for key,val in (("generated",generated),("completed",completed),
                        ("distance_m",dist),("energy_wh",env.total_energy_consumed),
                        ("avg_delay_s",stats["avg_delay"]),
                        ("swap_sessions",env.total_swap_sessions)):
            same("P1.2 original "+key,val,original[key])
    elif count["unpaid_leg_events"]>0:
        raise AssertionError("[P2_3_GATE_ALLOWED_UNPAID_FLIGHT]")

    row=dict(profile=args.profile,seed=args.seed,version=version,
             code_sha=wanted,experiment_sha=args.source_sha,
             config_sha256=config_hash,tape_sha256=tape_hash,
             mode="assigned",generated=generated,completed=completed,
             completion_rate=completed/generated,
             unfinished=generated-completed,
             avg_delay_s=float(stats["avg_delay"]),
             timeout_completed_only=float(stats["timeout_rate"]),
             energy_wh=float(env.total_energy_consumed),
             swap_sessions=int(env.total_swap_sessions),
             distance_m=dist,empty_ratio=(float(env.total_empty_distance)/dist if dist else 0),
             max_queue=maxqueue,
             unpaid_leg_events=int(count["unpaid_leg_events"]),
             unpaid_shortfall_wh=float(count["unpaid_shortfall_wh"]),
             blocked_attempts=int(count["blocked_attempts"]),
             blocked_drone_seconds=int(count["blocked_drone_seconds"]),
             blocked_drone_count=len(blocked_drones),
             blocked_at_end=sum(bool(getattr(d,"flight_energy_blocked",False)) for d in env.drones))
    for name in METRICS:
        if not math.isfinite(float(row[name])):
            raise AssertionError("[P2_3_NONFINITE] "+name)
    put(Path(args.outdir)/"runs"/("%s-%d-%s.json"%(args.profile,args.seed,version)),row)
    print("[P2_3_EPISODE] "+canonical(row),flush=True)


def shard(args):
    old=Path(args.old_root).resolve()
    new=Path(args.new_root).resolve()
    out=Path(args.outdir).resolve()
    if gitsha(old)!=BEFORE or gitsha(new)!=AFTER:
        raise AssertionError("[P2_3_WORKTREE_MISMATCH]")
    config,_=prepare(new,args.profile,out/"configs")
    for seed in SEEDS[args.shard*5:(args.shard+1)*5]:
        tape=make_tape(old,config,seed)
        tape_file=out/"tapes"/("tape-%s-%d.json"%(args.profile,seed))
        put(tape_file,{"seed":seed,"profile":args.profile,"tasks":tape,
                       "tape_sha256":fingerprint(tape)})
        for version,root in (("before",old),("after",new)):
            cmd=[sys.executable,str(Path(__file__).resolve()),"simulate",
                 "--root",str(root),"--config",str(config),
                 "--tape",str(tape_file),"--profile",args.profile,
                 "--seed",str(seed),"--version",version,
                 "--evidence-root",str(Path(args.evidence_root).resolve()),
                 "--source-sha",args.source_sha,"--outdir",str(out)]
            env=os.environ.copy()
            env["SWARM_BALANCE_SIM_CONFIG"]=str(config)
            env["SWARM_BALANCE_ENERGY_ACCOUNTING"]="assigned"
            subprocess.run(cmd,cwd=root,env=env,check=True)
    print("[P2_3_SHARD_COMPLETE] profile=%s shard=%d episodes=10"%
          (args.profile,args.shard),flush=True)


def aggregate(args):
    out=Path(args.outdir).resolve()
    rows=[read(p) for p in out.rglob("runs/*.json")]
    indexes=[(r["profile"],r["seed"],r["version"]) for r in rows]
    expected={(p,s,v) for p in PROFILES for s in SEEDS for v in ("before","after")}
    if len(rows)!=60 or set(indexes)!=expected or len(set(indexes))!=60:
        raise AssertionError("[P2_3_INCOMPLETE] found=%d"%len(rows))
    byid=dict(zip(indexes,rows))
    pairs=[]
    groups=[]
    for profile in PROFILES:
        sub=[]
        for seed in SEEDS:
            a=byid[profile,seed,"before"]
            b=byid[profile,seed,"after"]
            for key in ("generated","tape_sha256","config_sha256","mode","experiment_sha"):
                if a[key]!=b[key]:
                    raise AssertionError("[P2_3_UNPAIRED] "+key)
            if a["code_sha"]!=BEFORE or b["code_sha"]!=AFTER or a["experiment_sha"]!=args.source_sha:
                raise AssertionError("[P2_3_SOURCE_SHA_DRIFT]")
            pair={"profile":profile,"seed":seed,"before":a,"after":b,
                  "delta":{m:b[m]-a[m] for m in METRICS}}
            pairs.append(pair)
            sub.append(pair)
        group={"profile":profile,"seed_count":10,
               "demand_mean":statistics.mean(p["before"]["generated"] for p in sub),
               "old_unpaid_leg_events_mean":statistics.mean(p["before"]["unpaid_leg_events"] for p in sub),
               "new_blocked_attempts_mean":statistics.mean(p["after"]["blocked_attempts"] for p in sub),
               "new_affected_drones_mean":statistics.mean(p["after"]["blocked_drone_count"] for p in sub),
               "deltas":{m:{"mean":statistics.mean(p["delta"][m] for p in sub),
                            "sd":statistics.stdev(p["delta"][m] for p in sub),
                            "min":min(p["delta"][m] for p in sub),
                            "max":max(p["delta"][m] for p in sub)} for m in METRICS}}
        groups.append(group)
        print("[P2_3_AGG] "+canonical(group),flush=True)

    put(out/"p2_3_summary.json",{"source_sha":args.source_sha,"old_sha":BEFORE,
        "new_sha":AFTER,"episodes":60,"pairs":30,"groups":groups,
        "limitations":["Unpaid legacy flight counted only when debit routine reports shortfall.",
        "Blocked attempts are repeated drone-step attempts, not distinct tasks.",
        "No rescue, recharge-when-stranded, or automatic requeue is implemented.",
        "Timeout rate is conditional on completed tasks; keep unfinished alongside.",
        "This compares physical-feasibility logic in a simulator, not actual aircraft."]})
    cols=["profile","seed","version","generated","completed","completion_rate",
          "unfinished","avg_delay_s","timeout_completed_only","energy_wh",
          "swap_sessions","distance_m","max_queue","unpaid_leg_events",
          "unpaid_shortfall_wh","blocked_attempts","blocked_drone_seconds",
          "blocked_drone_count","blocked_at_end","code_sha","tape_sha256","config_sha256"]
    with (out/"p2_3_all_60_episodes.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=cols)
        w.writeheader()
        for row in sorted(rows,key=lambda r:(list(PROFILES).index(r["profile"]),r["seed"],r["version"])):
            w.writerow({k:row[k] for k in cols})
    md=["# P2.3 physical feasibility: old/new immutable code compare","",
        "Old `%s` vs new `%s`; Greedy and assigned energy only."%(BEFORE,AFTER),
        "Same frozen tape and SHA per paired seed, original P1.2 control replay asserted.",
        "",
        "| Scenario | Mean demand | Completion Δ pp | Unfinished Δ | Old unpaid leg events | New blocked attempts | Delay Δ s | Energy Δ Wh |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in groups:
        d=x["deltas"]
        md.append("| %s | %.1f | %+.3f | %+.2f | %.2f | %.2f | %+.2f | %+.2f |"%(
            x["profile"],x["demand_mean"],100*d["completion_rate"]["mean"],
            d["unfinished"]["mean"],x["old_unpaid_leg_events_mean"],
            x["new_blocked_attempts_mean"],d["avg_delay_s"]["mean"],
            d["energy_wh"]["mean"]))
    md+=["","Old completion metrics may include energetically impossible legs;",
          "this is a physical-feasibility gate only, NOT a complete safety/rescue mechanism.",
          "Compare per-seed rows and hashes in p2_3_all_60_episodes.csv and p2_3_summary.json."]
    (out/"p2_3_report.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    print("[P2_3_COMPLETE] episodes=60 pairs=30 profiles=3",flush=True)


def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    for command in ("shard","simulate","aggregate"):
        q=sub.add_parser(command)
        q.add_argument("--root",default=".")
        q.add_argument("--outdir",default=".")
        q.add_argument("--source-sha",required=True)
        if command in ("shard","simulate"):
            q.add_argument("--profile",required=True,choices=list(PROFILES))
        if command=="shard":
            q.add_argument("--old-root",required=True)
            q.add_argument("--new-root",required=True)
            q.add_argument("--evidence-root",required=True)
            q.add_argument("--shard",required=True,type=int,choices=(0,1))
        elif command=="simulate":
            q.add_argument("--config",required=True)
            q.add_argument("--tape",required=True)
            q.add_argument("--version",required=True,choices=("before","after"))
            q.add_argument("--evidence-root",required=True)
            q.add_argument("--seed",required=True,type=int)
    a=p.parse_args()
    if a.command=="shard":
        shard(a)
    elif a.command=="simulate":
        simulate(a)
    else:
        aggregate(a)


if __name__=="__main__":
    main()
