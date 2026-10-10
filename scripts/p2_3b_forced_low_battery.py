# -*- coding: utf-8 -*-
"""P2.3b: forced-low-battery diagnostic with real Drone.update/Environment.step.
Always execute *separate immutable Git checkouts*; never patch energy gate.
This is a controlled physical-contract test, NOT a representative city-wide KPI.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys

OLD="806d07653af52b83202ba232cb1f3e88dd9b7901"
NEW="5bcc6cb9661dc250c11c578acbacc32c8b0d6f4f"
CASES={"empty":0.0,"short":0.2,"exact":1.2,"ample":3.0}


def worker(args):
    root=Path(args.root).resolve()
    actual=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if actual!={"before":OLD,"after":NEW}[args.version]:
        raise AssertionError("[P23B_SHA_MISMATCH]")
    os.chdir(root)
    sys.path.insert(0,str(root))
    sys.path.insert(0,str(root/"frontend"))
    from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit
    LoadEnergyLedgerAudit.setUpClass()
    h=LoadEnergyLedgerAudit()
    battery=CASES[args.case]
    d=h.drone(load=0.0,battery=5.0,base=0.06)
    d.current_battery=battery
    d.scheduled_position=[(20.0,0.0,"waypoint"),(40.0,0.0,"waypoint")]
    env=h.small_environment(d)
    traces=[]
    for step in (1,2):
        last=(float(d.x),float(d.y))
        before_battery=float(d.current_battery)
        env.step({})
        traces.append(dict(step=step,moved_m=math.dist(last,(d.x,d.y)),
                           pos=[d.x,d.y],battery_before_wh=before_battery,
                           battery_after_wh=float(d.current_battery),
                           required_wh=float(d.last_energy_required_wh),
                           debited_wh=float(d.last_energy_debited_wh),
                           shortfall_wh=float(d.last_energy_shortfall_wh),
                           blocked=bool(getattr(d,"flight_energy_blocked",False)),
                           remaining_waypoints=len(d.scheduled_position),
                           consumed_waypoints=len(d.consumed_waypoints_this_step)))
    data=dict(case=args.case,version=args.version,code_sha=actual,
              initial_battery_wh=battery,steps=traces,
              total_distance_m=float(env.total_flight_distance),
              total_energy_wh=float(env.total_energy_consumed),
              unfinished_route=len(d.scheduled_position))
    print("[P23B_EPISODE] "+json.dumps(data,sort_keys=True,ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--worker",action="store_true")
    p.add_argument("--root")
    p.add_argument("--version",choices=("before","after"))
    p.add_argument("--case",choices=tuple(CASES))
    p.add_argument("--old-root")
    p.add_argument("--new-root")
    p.add_argument("--output")
    args=p.parse_args()
    if args.worker:
        worker(args)
        return
    out=Path(args.output).resolve()
    rows=[]
    for name,battery in CASES.items():
        for version,root in (("before",args.old_root),("after",args.new_root)):
            proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),
                  "--worker","--root",str(root),"--version",version,"--case",name],
                  text=True,capture_output=True,check=True)
            line=next((x for x in proc.stdout.splitlines()
                       if x.startswith("[P23B_EPISODE] ")),None)
            if not line:
                raise AssertionError("[P23B_NO_WITNESS] "+proc.stdout[-500:])
            rows.append(json.loads(line[len("[P23B_EPISODE] "):]))
    for name in CASES:
        a=next(x for x in rows if x["case"]==name and x["version"]=="before")
        b=next(x for x in rows if x["case"]==name and x["version"]=="after")
        for row in (a,b):
            if abs(sum(t["moved_m"] for t in row["steps"])-row["total_distance_m"])>1e-6:
                raise AssertionError("[P23B_DISTANCE_LEDGER]")
        if name in ("empty","short"):
            if not (a["total_distance_m"]==40.0 and b["total_distance_m"]==0.0):
                raise AssertionError("[P23B_NOT_ACTIVATED] "+name)
            if not all(t["blocked"] and t["debited_wh"]==0.0 and t["consumed_waypoints"]==0
                       for t in b["steps"]):
                raise AssertionError("[P23B_GATE_CONTRACT] "+name)
            if b["unfinished_route"]!=2 or a["unfinished_route"]!=0:
                raise AssertionError("[P23B_ROUTE_GATE] "+name)
        if name=="ample" and (a["total_distance_m"]!=40.0 or b["total_distance_m"]!=40.0):
            raise AssertionError("[P23B_CONTROL]")
        if name=="exact" and not (a["total_distance_m"]==40.0 and b["total_distance_m"]==20.0):
            raise AssertionError("[P23B_SECOND_STEP_GATE]")
    result={"old_sha":OLD,"new_sha":NEW,"cases":list(CASES),"observations":rows,
            "scope":"Controlled small Environment.step shell, NOT demand/distribution pressure comparison",
            "limitation":"No task requeue, landing, real aircraft or charging strategy; artificial starting battery levels"}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    for row in rows:
        print("[P23B_EPISODE] "+json.dumps(row,sort_keys=True),flush=True)
    print("[P23B_TRIGGER_PASS] cases=4 episodes=8 old_unpaid_motion_detected=true new_blocked_motion_detected=true",flush=True)


if __name__=="__main__":
    main()
