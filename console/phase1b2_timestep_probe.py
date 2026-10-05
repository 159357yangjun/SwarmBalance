# -*- coding: utf-8 -*-
"""G12 探针：ETA 的单位必须是 env-step —— time_step 翻倍时 ETA 必须减半。

若实现写成 `distance/speed`（漏除 STEP_SECONDS），两次读数会相同 ⇒ G12 红。
判据形状来自登记表 M5 的同族缺陷（分子按步、分母按秒，只在 time_step=1.0 时凑巧一致）。

STEP_SECONDS 同样是 import 期冻结（frontend/drone.py:22）⇒ 每个取值起一个子进程。
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]


def run_one(time_step, wd):
    cfg = json.loads((REPO / "config" / "simulation.json").read_text(encoding="utf-8"))
    cfg.setdefault("drone", {})["time_step"] = time_step
    f = wd / ("s_%s.json" % time_step)
    f.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    code = (
        "import os,sys,pathlib;"
        "R=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(R/'frontend'));"
        "os.environ['SWARM_BALANCE_SIM_CONFIG']=sys.argv[2];"
        "import drone;"
        "from route_cost import EuclideanRouteCostProvider, PlannedDistanceRouteCostProvider;"
        "p=EuclideanRouteCostProvider();"
        "eta=p.eta((0.0,0.0),(100.0,0.0),20.0);"
        "print('TS=%r STEP=%r ETA=%r' % (float(os.environ.get('TS')), drone.STEP_SECONDS, eta))"
    )
    env = dict(os.environ)
    env["TS"] = str(time_step)
    env.pop("SWARM_BALANCE_REACH_WEIGHT", None)
    proc = subprocess.run([sys.executable, "-X", "utf8", "-c", code, str(REPO), str(f)],
                          cwd=str(REPO), env=env, text=True, capture_output=True,
                          timeout=600, errors="replace")
    return proc.stdout.strip() + proc.stderr.strip()


def main():
    wd = pathlib.Path(tempfile.mkdtemp(prefix="p2ts_"))
    try:
        # 读数行必须直接进 stdout：测试侧按 `TS=` 前缀取数，套一层 list/repr 就解析不出。
        for ts in (1.0, 2.0):
            out = run_one(ts, wd)
            lines = [l for l in out.splitlines() if l.startswith("TS=")]
            if lines:
                print(lines[0])
            else:
                print("NO_READOUT " + out[-200:])
        return 0
    finally:
        shutil.rmtree(wd, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
