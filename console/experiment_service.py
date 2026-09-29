"""Web 控制台的一键实验服务。

只负责启动/查询独立的 ExperimentRunner 子进程；不会占用当前 SimSession，也不会
改写 simulation.json，因此用户可以把“自由仿真”和“批量评测”视为两个互不污染
的入口。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRESET_DIR = PROJECT_ROOT / "experiments" / "presets"
RESULT_ROOT = PROJECT_ROOT / "results" / "experiments"
STATUS_FILE = RESULT_ROOT / "web_status.json"
LOG_FILE = RESULT_ROOT / "web_runner.log"

_process: Optional[subprocess.Popen] = None
_log_handle = None


def presets() -> List[Dict[str, Any]]:
    from experiments.runner import build_plan
    out = []
    for p in sorted(PRESET_DIR.glob("*.yaml")):
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        out.append({
            "key": p.stem,
            "name": cfg.get("name", p.stem),
            "description": cfg.get("description", ""),
            "runs": len(build_plan(cfg)),
        })
    return out


def _read_status() -> Dict[str, Any]:
    if not STATUS_FILE.exists():
        return {"state": "idle", "progress": 0.0, "completed_runs": 0, "total_runs": 0}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "unknown", "progress": 0.0, "completed_runs": 0, "total_runs": 0}


def status() -> Dict[str, Any]:
    global _process, _log_handle
    data = _read_status()
    if _process is not None:
        code = _process.poll()
        if code is not None:
            _process = None
            if _log_handle is not None:
                try:
                    _log_handle.close()
                except Exception:
                    pass
                _log_handle = None
            # 如果进程异常终止且 runner 来不及写 failed 状态，补一个可见状态。
            if data.get("state") in {"starting", "running"}:
                data["state"] = "failed"
                data["error"] = f"实验子进程异常退出，exit={code}；详见 {LOG_FILE}"
                STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from build_conclusion_package import latest_conclusion_experiment
        latest = latest_conclusion_experiment()
        data["conclusion_package_available"] = bool(latest)
        data["conclusion_experiment"] = latest.name if latest else ""
    except Exception:
        data["conclusion_package_available"] = False
        data["conclusion_experiment"] = ""
    return data


def start(preset: str) -> Dict[str, Any]:
    global _process, _log_handle
    allowed = {p["key"] for p in presets()}
    if preset not in allowed:
        raise ValueError(f"未知实验预设: {preset}")
    if _process is not None and _process.poll() is None:
        raise RuntimeError("已有一键实验正在运行")

    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    initial = {
        "state": "starting",
        "preset": preset,
        "progress": 0.0,
        "completed_runs": 0,
        "total_runs": 0,
        "current": "正在启动实验进程",
    }
    STATUS_FILE.write_text(json.dumps(initial, ensure_ascii=False, indent=2), encoding="utf-8")
    if _log_handle is not None:
        try:
            _log_handle.close()
        except Exception:
            pass
    _log_handle = open(LOG_FILE, "a", encoding="utf-8")
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "run_conclusion.py"),
        "--preset", preset,
        "--output-root", str(RESULT_ROOT),
        "--status-file", str(STATUS_FILE),
    ]
    if preset == "conclusion":
        # 页签上点「一键结项实验」是用户的明确动作，且页面承诺跑完对比页会显示最近一次
        # 正式结果，所以这里显式带上发布开关；命令行默认不带，是为了评审照 README 跑
        # 一遍时不去截断重写已入库的 results/compare/one_click_latest.csv。
        cmd.append("--publish-latest")
    _process = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=_log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    initial["pid"] = _process.pid
    STATUS_FILE.write_text(json.dumps(initial, ensure_ascii=False, indent=2), encoding="utf-8")
    return initial
