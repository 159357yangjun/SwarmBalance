# -*- coding: utf-8 -*-
"""G14 探针：`config.environment.greedy.reach_weight` 与环境变量各自的优先级。

用法：python console/phase1b2_switch_probe.py <off|config|env|both>
输出：`W=<实得> WANT=<期望>`（由 test_phase1b2_eta.ConfigSwitchIsLive 解析）

为什么必须是独立文件而不是 `python -c "<一长串>"`：本机 shell 的引号嵌套会把分号拼接的
if/elif 截成一行 ⇒ SyntaxError（本轮实测撞过）。REACH_WEIGHT 在 import 期冻结，所以每个
mode 都要一个干净进程。
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "frontend"))

MODE = sys.argv[1] if len(sys.argv) > 1 else "off"


def main():
    cfg = json.loads((REPO / "config" / "simulation.json").read_text(encoding="utf-8"))
    greedy = cfg.setdefault("environment", {}).setdefault("greedy", {})
    want = 0.0
    if MODE == "config":
        greedy["reach_weight"] = 1.2
        want = 1.2
    elif MODE == "both":
        greedy["reach_weight"] = 0.4          # config 给一个值……
        want = 1.2                            # ……但 env 必须赢
    elif MODE == "env":
        want = 1.2
    elif MODE != "off":
        raise SystemExit("[BAD_MODE] %r" % MODE)

    wd = pathlib.Path(tempfile.mkdtemp(prefix="p2sw_"))
    f = wd / "s.json"
    f.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(f)
    os.environ.pop("SWARM_BALANCE_REACH_WEIGHT", None)
    if MODE in ("env", "both"):
        os.environ["SWARM_BALANCE_REACH_WEIGHT"] = "1.2"
    try:
        from greedy.scheduler import REACH_WEIGHT
        print("W=%r WANT=%r" % (REACH_WEIGHT, want))
        return 0 if abs(float(REACH_WEIGHT) - want) < 1e-12 else 1
    finally:
        shutil.rmtree(wd, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
