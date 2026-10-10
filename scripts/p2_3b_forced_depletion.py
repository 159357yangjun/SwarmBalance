# -*- coding: utf-8 -*-
"""P2.3b: forced mid-route battery depletion in identical P2.1/P2.2 simulators.

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
        raise AssertionError("[P23B_WRONG_WORKTREE]")
    cfg=Path(args.config).resolve()
    install(root,cfg)
    os.environ["SWARM_BALANCE_ENERGY_ACCOUNTING"]="assigned"
    from environment import Environment
    from greedy.scheduler import greedy_action_from_observation
    from drone import Drone
    data=read(args.tape)
    records=data["tasks"]
    tape_hash=fingerprint(records)
    config_hash=fingerprint(read(cfg))
    original=refrow(Path(args.evidence_root).resolve(),args.profile,args.seed)
    if tape_hash!=data["tape_sha256"] or original["tape_sha256"]!=tape_hash or original["config_sha256"]!=config_hash:
        raise AssertionError("[P23B_INPUT_DRIFT]")
    count=defaultdict(float)
    blocked_drones=set()
    blocked_tasks=set()
    blocked_this_step=set()
    fault=[]
    env_ref=[None]
    original_update=Drone.update
    original_consume=Drone.consume_battery
    original_gate=getattr(Drone,"_flight_step_feasible",None)

    def inject_once(drone,*a,**kw):
        # Deliberate fault intervention, not a real battery model.
        # Select the earliest task-active drone that is away from a nest.
        if (not fault and drone.scheduled_position
                and drone.executing_task_id is not None
                and not drone.is_charging
                and not getattr(drone,"out_of_service",False)):
            stations=getattr(drone,"known_stations",None) or []
            distances=[math.dist(drone.get_position(),st.get_position()) for st in stations]
            if distances and min(distances)>100.0:
                old_wh=float(drone.current_battery)
                fault.append({
                    "step":float(env_ref[0].current_time),
                    "drone_id":str(drone.drone_id),
                    "task_id":str(drone.executing_task_id),
                    "x":float(drone.x),"y":float(drone.y),
                    "target":list(drone.scheduled_position[0]),
                    "battery_before_wh":old_wh,
                    "fault_removed_wh":old_wh,
                    "battery_after_fault_wh":0.0,
                    "nearest_station_m":min(distances)
                })
                drone.current_battery=0.0
        return original_update(drone,*a,**kw)

    def monitor_consume(drone,distance,wind_along=None):
        used=original_consume(drone,distance,wind_along)
        if distance>0 and drone.last_energy_shortfall_wh>1e-9:
            count["unpaid_leg_events"]+=1
            count["unpaid_shortfall_wh"]+=float(drone.last_energy_shortfall_wh)
        return used

    def monitor_gate(drone,distance,wind_along):
        allowed=original_gate(drone,distance,wind_along)
        if not allowed:
            count["blocked_attempts"]+=1
            blocked_drones.add(str(drone.drone_id))
            blocked_this_step.add(str(drone.drone_id))
            if drone.executing_task_id is not None:
                blocked_tasks.add(str(drone.executing_task_id))
        return allowed

    Drone.update=inject_once
    Drone.consume_battery=monitor_consume
    if version=="after":
        if original_gate is None:
            raise AssertionError("[P23B_GATE_MISSING]")
        Drone._flight_step_feasible=monitor_gate
    elif original_gate is not None:
        raise AssertionError("[P23B_OLD_GATE_UNEXPECTED]")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            osm=root/"frontend"/"data"/"map"/"part_of_yangpu.osm"
            env=Environment(str(osm),episode_max_steps=HORIZON)
            env.task_generator=FrozenTaskSource(records)
            env_ref[0]=env
            obs=env.reset(seed=args.seed)
            done=False
            max_queue=len(env.task_generator.unassigned_tasks)
            while not done:
                blocked_this_step.clear()
                action=greedy_action_from_observation(obs)
                obs,_,done,_=env.step(action)
                count["blocked_drone_seconds"]+=len(blocked_this_step)
                max_queue=max(max_queue,len(env.task_generator.unassigned_tasks))
            stats=env.get_statistics()
    finally:
        Drone.update=original_update
        Drone.consume_battery=original_consume
        if version=="after":
            Drone._flight_step_feasible=original_gate

    if len(fault)!=1:
        raise AssertionError("[P23B_NO_FAULT] injected=%d"%len(fault))
    if version=="before" and count["unpaid_leg_events"]<1:
        raise AssertionError("[P23B_NO_OLD_UNPAID_FLIGHT]")
    if version=="after" and (count["blocked_attempts"]<1 or count["unpaid_leg_events"]!=0):
        raise AssertionError("[P23B_NEW_GATE_NOT_EXERCISED]")
    generated=int(env.total_generated_tasks)
    completed=int(env.total_completed_tasks)
    if generated!=len(records) or len(env.generated_task_times)!=generated:
        raise AssertionError("[P23B_GENERATION_LEDGER]")
    distance=float(env.total_flight_distance)
    same("distance ledger",distance,float(env.total_empty_distance)+float(env.total_loaded_distance))
    row=dict(profile=args.profile,seed=args.seed,version=version,
        code_sha=wanted,experiment_sha=args.source_sha,
        config_sha256=config_hash,tape_sha256=tape_hash,
        fault=fault[0],mode="assigned",
        generated=generated,completed=completed,
        completion_rate=completed/generated,unfinished=generated-completed,
        avg_delay_s=float(stats["avg_delay"]),
        timeout_completed_only=float(stats["timeout_rate"]),
        energy_wh=float(env.total_energy_consumed),
        swap_sessions=int(env.total_swap_sessions),
        distance_m=distance,
        empty_ratio=(float(env.total_empty_distance)/distance if distance else 0),
        max_queue=max_queue,
        unpaid_leg_events=int(count["unpaid_leg_events"]),
        unpaid_shortfall_wh=float(count["unpaid_shortfall_wh"]),
        blocked_attempts=int(count["blocked_attempts"]),
        blocked_drone_seconds=int(count["blocked_drone_seconds"]),
        blocked_drone_count=len(blocked_drones),
        blocked_distinct_tasks=len(blocked_tasks),
        blocked_at_end=sum(bool(getattr(d,"flight_energy_blocked",False)) for d in env.drones))
    for key in METRICS:
        if not math.isfinite(float(row[key])):
            raise AssertionError("[P23B_NONFINITE] "+key)
    put(Path(args.outdir)/"runs"/("%s-%d-%s.json"%(args.profile,args.seed,version)),row)
    print("[P23B_EPISODE] "+canonical(row),flush=True)



def shard(args):
    old=Path(args.old_root).resolve()
    new=Path(args.new_root).resolve()
    out=Path(args.outdir).resolve()
    if gitsha(old)!=BEFORE or gitsha(new)!=AFTER:
        raise AssertionError("[P23B_SOURCE_DRIFT]")
    config,_=prepare(new,args.profile,out/"configs")
    seeds=SEEDS[args.shard*5:(args.shard+1)*5]
    if args.seed_only is not None:
        if args.seed_only not in seeds:
            raise AssertionError("[P23B_SEED_OUT_OF_SHARD]")
        seeds=[args.seed_only]
    for seed in seeds:
        tape=make_tape(old,config,seed)
        path=out/"tapes"/("tape-%s-%d.json"%(args.profile,seed))
        put(path,{"seed":seed,"profile":args.profile,
                  "tasks":tape,"tape_sha256":fingerprint(tape)})
        for version,root in (("before",old),("after",new)):
            cmd=[sys.executable,str(Path(__file__).resolve()),"simulate",
                 "--root",str(root),"--config",str(config),"--tape",str(path),
                 "--profile",args.profile,"--seed",str(seed),
                 "--version",version,"--evidence-root",str(Path(args.evidence_root).resolve()),
                 "--outdir",str(out),"--source-sha",args.source_sha]
            env=os.environ.copy()
            env["SWARM_BALANCE_SIM_CONFIG"]=str(config)
            env["SWARM_BALANCE_ENERGY_ACCOUNTING"]="assigned"
            subprocess.run(cmd,cwd=root,env=env,check=True)
        a=read(out/"runs"/("%s-%d-before.json"%(args.profile,seed)))
        b=read(out/"runs"/("%s-%d-after.json"%(args.profile,seed)))
        for key in ("step","drone_id","task_id","x","y","target",
                    "battery_before_wh","fault_removed_wh"):
            if a["fault"][key]!=b["fault"][key]:
                raise AssertionError("[P23B_DIFFERENT_FAULT] "+key)
        if a["unpaid_leg_events"]<1 or b["blocked_attempts"]<1:
            raise AssertionError("[P23B_NEGATIVE_CONTROL]")
        print("[P23B_PAIR_PASS] "+canonical({
            "seed":seed,"profile":args.profile,
            "fault_step":a["fault"]["step"],
            "old_unpaid":a["unpaid_leg_events"],
            "new_blocked":b["blocked_attempts"]}),flush=True)
    print("[P23B_SHARD_COMPLETE] profile=%s shard=%d pairs=%d"%(
        args.profile,args.shard,len(seeds)),flush=True)



def aggregate(args):
    out=Path(args.outdir).resolve()
    episodes=[read(p) for p in out.rglob("runs/*.json")]
    keys=[(r["profile"],r["seed"],r["version"]) for r in episodes]
    expected={(p,s,v) for p in PROFILES for s in SEEDS for v in ("before","after")}
    if len(episodes)!=60 or len(set(keys))!=60 or set(keys)!=expected:
        raise AssertionError("[P23B_INCOMPLETE] episodes=%d unique=%d"%(len(episodes),len(set(keys))))
    ix=dict(zip(keys,episodes))
    pairs=[]
    groups=[]
    for profile in PROFILES:
        bucket=[]
        for seed in SEEDS:
            a=ix[profile,seed,"before"]
            b=ix[profile,seed,"after"]
            for key in ("generated","tape_sha256","config_sha256","experiment_sha"):
                if a[key]!=b[key]:
                    raise AssertionError("[P23B_UNPAIRED_INPUT] "+key)
            if a["code_sha"]!=BEFORE or b["code_sha"]!=AFTER or a["experiment_sha"]!=args.source_sha:
                raise AssertionError("[P23B_WRONG_SHA]")
            for key in ("step","drone_id","task_id","x","y","target",
                        "battery_before_wh","fault_removed_wh"):
                if a["fault"][key]!=b["fault"][key]:
                    raise AssertionError("[P23B_FAULT_MOMENT_DIFFERS] "+key)
            if a["unpaid_leg_events"]<1 or b["blocked_attempts"]<1 or b["unpaid_leg_events"]!=0:
                raise AssertionError("[P23B_NOT_TRIGGERED]")
            pair={"profile":profile,"seed":seed,"before":a,"after":b,
                  "delta":{k:b[k]-a[k] for k in METRICS}}
            pairs.append(pair)
            bucket.append(pair)
        group={
            "profile":profile,"paired_seeds":len(bucket),
            "mean_demand":statistics.mean(x["before"]["generated"] for x in bucket),
            "mean_fault_removed_wh":statistics.mean(x["before"]["fault"]["fault_removed_wh"] for x in bucket),
            "mean_old_unpaid_legs":statistics.mean(x["before"]["unpaid_leg_events"] for x in bucket),
            "mean_new_blocked_attempts":statistics.mean(x["after"]["blocked_attempts"] for x in bucket),
            "mean_new_blocked_distinct_tasks":statistics.mean(x["after"]["blocked_distinct_tasks"] for x in bucket),
            "deltas":{k:{"mean":statistics.mean(x["delta"][k] for x in bucket),
                          "sd":statistics.stdev(x["delta"][k] for x in bucket),
                          "min":min(x["delta"][k] for x in bucket),
                          "max":max(x["delta"][k] for x in bucket)} for k in METRICS}}
        groups.append(group)
        print("[P23B_AGG] "+canonical(group),flush=True)
    put(out/"p23b_summary.json",{
        "source_sha":args.source_sha,"before_sha":BEFORE,"after_sha":AFTER,
        "episodes":len(episodes),"pairs":len(pairs),"groups":groups,
        "injection":"one task-active drone >100m from all swap nests, once per run, battery forced to exactly zero Wh",
        "warnings":["Artificial battery loss is excluded from flight energy consumed.",
                    "This test forces a rare fault; not an estimate of real fault frequency.",
                    "Blocked attempts are drone steps, not unique orders.",
                    "Old completion may use energy-shortfall legs which are physically impossible.",
                    "No emergency landing, rescue, or automatic requeue is implemented."]})
    columns=["profile","seed","version","generated","completed","completion_rate",
             "unfinished","avg_delay_s","timeout_completed_only","energy_wh",
             "swap_sessions","distance_m","max_queue","unpaid_leg_events",
             "unpaid_shortfall_wh","blocked_attempts","blocked_drone_seconds",
             "blocked_drone_count","blocked_distinct_tasks","blocked_at_end",
             "code_sha","tape_sha256","config_sha256"]
    with (out/"p23b_60_episodes.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=columns)
        w.writeheader()
        for e in sorted(episodes,key=lambda e:(list(PROFILES).index(e["profile"]),e["seed"],e["version"])):
            w.writerow({k:e[k] for k in columns})
    report=["# P2.3b – forced in-flight depletion (assigned only)","",
            "P2.1 original vs P2.2 real gate, same order tapes and seeded configuration.",
            "Exactly one task-active drone receives an injected zero-Wh battery state >100m from a nest.",
            "Fault injection records battery removed separately from simulated flight Wh.",
            "",
            "| Scenario | Old unpaid legs | New blocked step attempts | Completion delta pp | Unfinished delta | Delay delta s | Energy debit delta Wh |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for g in groups:
        d=g["deltas"]
        report.append("| %s | %.2f | %.2f | %+.3f | %+.2f | %+.2f | %+.2f |"%(
            g["profile"],g["mean_old_unpaid_legs"],g["mean_new_blocked_attempts"],
            100*d["completion_rate"]["mean"],d["unfinished"]["mean"],
            d["avg_delay_s"]["mean"],d["energy_wh"]["mean"]))
    report+=["","All numbers are simulation-only and conditioned on an artificial power-loss event.",
              "See per-seed CSV, raw JSON and tape fingerprints for audit."]
    (out/"p23b_report.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    print("[P23B_COMPLETE] episodes=60 pairs=30 forced_pairs=30",flush=True)



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
            q.add_argument("--seed-only",type=int)
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
