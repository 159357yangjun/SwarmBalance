# -*- coding: utf-8 -*-
"""Diagnostic-only counterfactual: isolate G2 speed input from battery depletion.

Not an acceptance substitute for production flight safety; NEVER bypasses gate.
Run immutable PSO/Environment; change only disposable test-scenario battery capacity.
"""
import os
import pathlib
import re
import shlex
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROBE = ROOT / "console" / "phase0_speed_gate_teeth_probe.py"


def run(face):
    env = dict(os.environ, SWARM_G2_DIAG_BATTERY_SCALE="20.0")
    p = subprocess.run([sys.executable, str(PROBE), face], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900)
    lines = p.stdout.splitlines()
    telemetry = [s for s in lines if s.startswith("[G2_POLICY_TRACE]")]
    readings = [s for s in lines if s.startswith('TEETH face="')]
    for line in (telemetry + readings):
        print(line, flush=True)
    if p.returncode or len(telemetry) != 1 or len(readings) != 1:
        raise AssertionError("failed or missing measurements %s rc=%s: %s" %
                             (face, p.returncode, (p.stdout + p.stderr)[-700:]))
    kv = dict(token.split("=", 1) for token in shlex.split(readings[0])[1:])
    blocked = int(re.search(r"blocked_drone_steps=(\d+)", telemetry[0]).group(1))
    if blocked != 0:
        raise AssertionError("battery-normalized %s is STILL flight blocked %d" % (face, blocked))
    return kv


def main():
    faces = {face: run(face) for face in ("gate", "mutate", "noDenom")}
    g, m, n = (faces[x] for x in ("gate", "mutate", "noDenom"))
    gopt, mopt, nopt = (int(x["optimize_calls"]) for x in (g, m, n))
    ratio = mopt / gopt if gopt else float("inf")
    print("[G2_ENERGY_ISOLATION] 20x fixture battery; true safety gate active; "
          "gate=%d mutate=%d noDenom=%d ratio=%.5f" %
          (gopt, mopt, nopt, ratio), flush=True)
    assert gopt > 0, "denominator absent"
    assert int(m["flush_size"]) == 0, "size trigger unexpectedly active"
    assert nopt == 0, "noDenom unexpectedly invoked optimizer"
    assert mopt * 100 < gopt, "original <1% criterion not recovered"
    print("[G2_ENERGY_ISOLATION_PASS] all original structural criteria retained", flush=True)


if __name__ == "__main__":
    main()
