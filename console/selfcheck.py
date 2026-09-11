"""End-to-end headless self-check for the defense/demo machine.

This intentionally uses the real bundled OSM file and the real Environment rather than
mock objects. It validates the shortest critical path used by the Web console:
map load -> environment -> Greedy scheduling -> runtime task injection -> checkpoint
save/restore -> static map export.

Usage:
    python -m console.selfcheck
    python -m console.selfcheck --steps 20
"""
from __future__ import annotations

import argparse
import math
import time
from typing import Dict, List

from console.capabilities import runtime_capabilities
from console.preflight import run_checks


def _ok(label: str, detail: str = "") -> None:
    suffix = f" · {detail}" if detail else ""
    print(f"[OK] {label}{suffix}")


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise RuntimeError(message)


def run_selfcheck(steps: int = 12) -> Dict[str, object]:
    started = time.time()
    caps = runtime_capabilities()
    pre = run_checks(portable=True)
    if pre["errors"]:
        raise RuntimeError("便携预检失败：" + "；".join(pre["errors"]))
    for msg in pre["warnings"]:
        print(f"[WARN] {msg}")
    _ok("便携启动预检", f"地图后端={caps['map_backend_label']}")

    # Import only after lightweight preflight, so failures are easier to diagnose.
    from console.sim_session import SimSession

    session = SimSession(episode_max_steps=max(int(steps) + 20, 40))
    snap = session.reset("greedy", seed=20260911)
    _require(len(snap.get("drones") or []) > 0, "环境未生成无人机")
    _require(len(snap.get("tasks") or []) > 0, "环境未生成初始任务")
    bounds = (snap.get("map") or {}).get("bounds") or []
    _require(len(bounds) == 4 and all(math.isfinite(float(v)) for v in bounds), "地图边界无效")
    _ok("真实 Environment 初始化", f"无人机={len(snap['drones'])}，初始任务={len(snap['tasks'])}")

    static = session.map_static()
    _require(len(static.get("buildings") or []) > 0, "静态地图没有高层建筑几何")
    _ok("本地 OSM 地图解析", f"高层建筑={len(static['buildings'])}，禁飞区={len(static.get('no_fly_zones') or [])}")

    # 自检只验证关键链路，不做性能评测。先确认真实初始任务已生成，再将
    # 待调度池缩成一条人工任务，避免启动脚本为了 10+ 条任务的首轮 A* 分配
    # 等待十几秒。正式仿真/实验绝不会执行这段自检裁剪。
    session.env.task_generator.unassigned_tasks.clear()
    session.env.total_generated_tasks = 0
    session.env.generated_task_times = []
    session.obs = session.env._obs()
    before_pending = 0
    injected = session.inject_task(
        weight=1.0, volume=0.1, priority=3, deadline_offset=300,
        category="emergency", task_id="selfcheck_emergency",
    )
    _require(int(injected.get("pending_count", 0)) == 1, "运行中插单未进入待调度池")
    _ok("运行中紧急任务注入", "selfcheck_emergency")

    for _ in range(max(1, int(steps))):
        session.step()
        if session.done:
            break
    progressed = session.snapshot()
    _require(int(progressed.get("step", 0)) > 0, "仿真步未推进")
    _require(any(e.get("kind") in {"task_assigned", "task_injected", "task_generated"} for e in progressed.get("events", [])), "调度事件流为空")
    _ok("真实 Greedy 滚动调度", f"推进={progressed['step']} 步，事件={len(progressed.get('events', []))}")

    checkpoint_step = int(progressed["step"])
    session.save_checkpoint("selfcheck")
    session.step_many(2)
    _require(int(session.snapshot()["step"]) >= checkpoint_step, "检查点后仿真状态异常")
    restored = session.load_checkpoint("selfcheck")
    _require(int(restored["step"]) == checkpoint_step, "运行态快照未恢复到保存步数")
    _ok("运行态快照保存/恢复", f"step={checkpoint_step}")

    elapsed = round(time.time() - started, 3)
    _ok("端到端自检完成", f"{elapsed}s")
    return {
        "ok": True,
        "elapsed_seconds": elapsed,
        "map_backend": caps["map_backend"],
        "steps": checkpoint_step,
        "drones": len(restored.get("drones") or []),
        "buildings": len(static.get("buildings") or []),
        "warnings": pre["warnings"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="群智优衡 Web/仿真关键链路端到端自检")
    parser.add_argument("--steps", type=int, default=12, help="真实推进步数，默认 12")
    args = parser.parse_args()
    try:
        run_selfcheck(args.steps)
    except Exception as exc:
        print(f"[FAIL] {exc}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
