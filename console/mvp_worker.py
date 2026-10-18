"""每次运行一个独立进程；配置必须先于任何引擎模块导入。"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import traceback

from console.mvp_service import now, read_json, status_lock, write_json


def run(folder):
    folder = Path(folder).resolve()
    config_path = folder / "simulation.json"
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(config_path)
    status_path = folder / "status.json"
    status = read_json(status_path)

    def save(state, **fields):
        with status_lock(folder):
            current = read_json(status_path)
            if current["status"] in {"interrupted", "stopped"}:
                return False
            if (folder / "stop").exists():
                current.update(status="stopped", updated_at=now())
                write_json(status_path, current)
                return False
            status.update(status=state, updated_at=now(), **fields)
            write_json(status_path, status)
            return True

    def stopped():
        if (folder / "stop").exists():
            save("stopped")
            return True
        return False

    try:
        if stopped():
            return
        if not save("running", started_at=now()):
            return
        # 真实旧引擎：不重写调度、步进或指标。
        from console.sim_session import SimSession
        session = SimSession()
        project = read_json(folder / "project.json")
        snapshot = session.reset(algorithm=project["algorithm"], seed=project["seed"])
        from greedy import scheduler
        from config.config_loder import get_shared_config
        config = get_shared_config()
        engine_input = {
            "algorithm": session.algorithm, "seed": session.seed,
            "num_drones": session.num_drones, "episode_max_steps": session.episode_max_steps,
            "route_cost_kind": session.env.route_cost_kind,
            "greedy": {key: getattr(scheduler, key.upper())
                       for key in config["environment"]["greedy"]},
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "project_sha256": hashlib.sha256((folder / "project.json").read_bytes()).hexdigest(),
        }
        if not save("running", engine_input=engine_input):
            return
        while not session.done:
            if stopped():
                return
            snapshot = session.step()
            if session.step_count % 5 == 0 or session.done:
                if not save("running", step=session.step_count,
                            progress=min(1.0, session.step_count / session.episode_max_steps)):
                    return
        if stopped():
            return
        result = {"run_id": status["run_id"], "project_id": status["project_id"],
                  "project": project, "engine_input": engine_input,
                  "snapshot": snapshot, "finished_at": now()}
        write_json(folder / "result.json", result)
        save("completed", step=session.step_count, progress=1.0, finished_at=now())
        print(f"completed run_id={status['run_id']} steps={session.step_count} stats={snapshot['stats']}", flush=True)
    except Exception as exc:
        traceback.print_exc()
        save("failed", error=f"{type(exc).__name__}: {exc}", finished_at=now())
        raise


if __name__ == "__main__":
    run(sys.argv[1])
