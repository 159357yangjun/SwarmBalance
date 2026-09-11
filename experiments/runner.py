"""一键结项实验编排器。

设计原则
--------
* 不把系统变成“纯跑分工具”：正常 Web 仿真仍然自由播放/暂停/单步/调参。
* 实验模式只是把重复的“改场景 → 切算法 → 跑多次 → 汇总”自动化。
* 每个 episode 在独立子进程中运行，并通过环境变量读取独立配置副本，绝不改写
  ``config/simulation.json``，因此不会污染日常仿真配置。
* 所有算法使用同一批随机种子，保证横向比较公平。
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import shutil
import importlib.util
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRESET_DIR = Path(__file__).resolve().parent / "presets"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results" / "experiments"
DEFAULT_OSM = PROJECT_ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm"
BASE_CONFIG = PROJECT_ROOT / "config" / "simulation.json"

for p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "frontend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from metrics_schema import ALGORITHM_LABELS, METRIC_COLUMNS  # noqa: E402
from experiments.reporting import descriptive_stats, paired_comparison, render_paired_markdown, write_rows  # noqa: E402
from experiments.reproducibility import write_manifest  # noqa: E402


@dataclass
class RunSpec:
    index: int
    experiment: str
    variable: str
    value: str
    algorithm: str
    repeat: int
    seed: int
    patch: Dict[str, Any]


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def load_preset(name_or_path: str) -> Dict[str, Any]:
    p = Path(name_or_path)
    if not p.exists():
        p = PRESET_DIR / f"{name_or_path}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"找不到实验预设: {name_or_path}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    data["_preset_path"] = str(p.resolve())
    data["_preset_key"] = p.stem
    return data


def list_presets() -> List[Dict[str, Any]]:
    rows = []
    for p in sorted(PRESET_DIR.glob("*.yaml")):
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        plan = build_plan(cfg)
        rows.append({
            "key": p.stem,
            "name": cfg.get("name", p.stem),
            "description": cfg.get("description", ""),
            "runs": len(plan),
        })
    return rows


def _as_algorithms(section: Dict[str, Any], preset: Dict[str, Any]) -> List[str]:
    algs = section.get("algorithms") or preset.get("algorithms") or ["greedy", "ga", "ortools", "pso"]
    valid = {"greedy", "ga", "ortools", "pso"}
    return [a for a in algs if a in valid]


def build_plan(preset: Dict[str, Any]) -> List[RunSpec]:
    base = preset.get("base", {}) or {}
    base_seed = int(base.get("seed", 100))
    base_repeats = max(1, int(base.get("repeats", 1)))
    experiments = preset.get("experiments", {}) or {}
    plan: List[RunSpec] = []

    def add_block(exp_name: str, variable: str, value: Any, patch: Dict[str, Any], section: Dict[str, Any]):
        repeats = max(1, int(section.get("repeats", base_repeats)))
        algs = _as_algorithms(section, preset)
        # 同一 repeat 的不同算法共用完全相同 seed；不同实验块加稳定偏移，避免场景串用。
        exp_offset = {"algorithm_comparison": 0, "task_scale": 10000, "task_density": 15000, "nest_berths": 20000, "fleet_mix": 30000}.get(exp_name, 40000)
        for rep in range(repeats):
            # 敏感性实验不同参数值也复用同一组 Seed，尽量形成配对控制变量。
            seed = base_seed + exp_offset + rep + 1
            for alg in algs:
                plan.append(RunSpec(
                    index=len(plan) + 1,
                    experiment=exp_name,
                    variable=variable,
                    value=str(value),
                    algorithm=alg,
                    repeat=rep + 1,
                    seed=seed,
                    patch=copy.deepcopy(patch),
                ))

    sec = experiments.get("algorithm_comparison", {}) or {}
    if sec.get("enabled", True):
        add_block("algorithm_comparison", "场景", sec.get("label", "default"), {}, sec)

    sec = experiments.get("task_scale", {}) or {}
    if sec.get("enabled", False):
        for total in sec.get("values", []):
            total = int(total)
            add_block(
                "task_scale", "任务规模", total,
                {"task_generation": {"realistic": {"total_tasks": total}}}, sec,
            )

    sec = experiments.get("task_density", {}) or {}
    if sec.get("enabled", False):
        for item in sec.get("values", []):
            if isinstance(item, dict):
                scale = float(item.get("interval_scale", 1.0))
                name = str(item.get("name") or scale)
            else:
                scale = float(item)
                name = str(scale)
            add_block(
                "task_density", "任务密度", name,
                {"task_generation": {"realistic": {"interval_scale": scale}}}, sec,
            )

    sec = experiments.get("nest_berths", {}) or {}
    if sec.get("enabled", False):
        for berths in sec.get("values", []):
            berths = int(berths)
            add_block("nest_berths", "机巢泊位数", berths, {"nest": {"berths": berths}}, sec)

    sec = experiments.get("fleet_mix", {}) or {}
    if sec.get("enabled", False):
        for item in sec.get("values", []):
            name = str(item.get("name") or f"L{item.get('light_express',0)}-S{item.get('standard_cargo',0)}-H{item.get('heavy_cargo',0)}")
            mix = {
                "light_express": int(item.get("light_express", 0)),
                "standard_cargo": int(item.get("standard_cargo", 0)),
                "heavy_cargo": int(item.get("heavy_cargo", 0)),
            }
            num = sum(mix.values())
            add_block(
                "fleet_mix", "异构机队配比", name,
                {"environment": {"num_drones": num}, "heterogeneous": {"fleet_mix": mix}}, sec,
            )
    return plan


def _preflight(plan: List[RunSpec], osm_path: Path) -> None:
    missing = []
    for module in ("numpy", "yaml", "osmnx", "shapely", "networkx"):
        if importlib.util.find_spec(module) is None:
            missing.append(module)
    if any(r.algorithm == "ortools" for r in plan) and importlib.util.find_spec("ortools") is None:
        missing.append("ortools")
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise RuntimeError(
            f"实验依赖未安装：{names}。请按项目 README 使用 Python 3.10 环境执行 pip install -r requirements.txt。"
        )
    if not osm_path.exists():
        raise RuntimeError(f"OSM 地图不存在：{osm_path}")


def _status_write(path: Optional[Path], payload: Dict[str, Any]) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _mean_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, float]:
    rows = [r for r in rows if r.get("ok")]
    if not rows:
        return {c: 0.0 for c in METRIC_COLUMNS}
    return {c: sum(float(r.get(c, 0.0)) for r in rows) / len(rows) for c in METRIC_COLUMNS}


def _write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _aggregate(raw_rows: List[Dict[str, Any]], output_dir: Path) -> Dict[str, Path]:
    outputs: Dict[str, Path] = {}
    meta_cols = ["实验", "变量", "取值", "重复", "Seed", "算法key", "算法", "成功", "耗时秒", "错误"]
    _write_csv(output_dir / "raw_runs.csv", raw_rows, meta_cols + METRIC_COLUMNS)
    outputs["raw"] = output_dir / "raw_runs.csv"

    mapping = {
        "algorithm_comparison": ("algorithm_comparison.csv", None),
        "task_scale": ("task_scale.csv", "任务规模"),
        "task_density": ("task_density.csv", "任务密度"),
        "nest_berths": ("nest_capacity.csv", "机巢泊位数"),
        "fleet_mix": ("fleet_mix.csv", "异构机队配比"),
    }

    for exp, (filename, variable_name) in mapping.items():
        subset = [r for r in raw_rows if r["实验"] == exp and r["成功"]]
        if not subset:
            continue
        grouped: Dict[tuple, List[Dict[str, Any]]] = {}
        for row in subset:
            key = (row["取值"], row["算法key"]) if variable_name else (row["算法key"],)
            grouped.setdefault(key, []).append(row)
        out_rows = []
        for key, rows in grouped.items():
            metrics = _mean_rows(rows)
            if variable_name:
                value, alg = key
                record = {variable_name: value, "算法key": alg, "算法": ALGORITHM_LABELS.get(alg, alg), "重复次数": len(rows)}
            else:
                (alg,) = key
                record = {"算法key": alg, "算法": ALGORITHM_LABELS.get(alg, alg), "重复次数": len(rows)}
            record.update({c: round(metrics[c], 6) for c in METRIC_COLUMNS})
            out_rows.append(record)
        fields = ([variable_name] if variable_name else []) + ["算法key", "算法", "重复次数"] + METRIC_COLUMNS
        path = output_dir / filename
        _write_csv(path, out_rows, fields)
        outputs[exp] = path

    # 结项证据：在均值表之外保留离散程度，并利用同 Seed 做 GA vs Greedy 描述性配对。
    stats_rows = descriptive_stats(raw_rows)
    if stats_rows:
        stats_path = write_rows(output_dir / "algorithm_comparison_stats.csv", stats_rows)
        outputs["algorithm_comparison_stats"] = stats_path
    paired_rows = paired_comparison(raw_rows, candidate="ga", baseline="greedy")
    if paired_rows:
        paired_path = write_rows(output_dir / "paired_ga_vs_greedy.csv", paired_rows)
        outputs["paired_ga_vs_greedy"] = paired_path

    # 让已有“对比”页自动显示最近一次一键实验结果。只写算法对比汇总，不改历史文件。
    alg_path = outputs.get("algorithm_comparison")
    if alg_path:
        latest = PROJECT_ROOT / "results" / "compare" / "one_click_latest.csv"
        latest.parent.mkdir(parents=True, exist_ok=True)
        with open(alg_path, "r", encoding="utf-8-sig", newline="") as src:
            rows = list(csv.DictReader(src))
        latest_rows = []
        for row in rows:
            clean = {"算法": row.get("算法key") or row.get("算法", "")}
            clean.update({c: row.get(c, 0.0) for c in METRIC_COLUMNS})
            latest_rows.append(clean)
        _write_csv(latest, latest_rows, ["算法"] + METRIC_COLUMNS)
        outputs["compare_latest"] = latest
    return outputs


def _plot(outputs: Dict[str, Path], output_dir: Path) -> List[Path]:
    try:
        import pandas as pd
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
    except Exception as exc:
        print(f"[plot] 跳过绘图：{exc}")
        return []
    # 自动选择系统已有中文字体；不打包/复制任何字体文件。
    available = {f.name for f in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Serif CJK SC", "Noto Serif CJK JP", "Arial Unicode MS"):
        if candidate in available:
            plt.rcParams["font.sans-serif"] = [candidate]
            plt.rcParams["axes.unicode_minus"] = False
            break
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    made: List[Path] = []

    alg_path = outputs.get("algorithm_comparison")
    if alg_path and alg_path.exists():
        df = pd.read_csv(alg_path, encoding="utf-8-sig")
        for metric, filename, ylabel in [
            ("完成率", "algorithm_completion_rate.png", "Completion rate"),
            ("超时率", "algorithm_timeout_rate.png", "Timeout rate"),
            ("无人机利用率", "algorithm_utilization.png", "Drone utilization"),
            ("空载率", "algorithm_empty_load_ratio.png", "Empty-load ratio"),
        ]:
            if metric not in df.columns:
                continue
            fig, ax = plt.subplots(figsize=(8, 4.5))
            ax.bar(df["算法"].astype(str), df[metric].astype(float))
            ax.set_title(metric)
            ax.set_ylabel(ylabel)
            ax.tick_params(axis="x", rotation=20)
            fig.tight_layout()
            path = fig_dir / filename
            fig.savefig(path, dpi=160)
            plt.close(fig)
            made.append(path)

    for key, xcol, filename in [
        ("task_scale", "任务规模", "sensitivity_task_scale.png"),
        ("task_density", "任务密度", "sensitivity_task_density.png"),
        ("nest_berths", "机巢泊位数", "sensitivity_nest_berths.png"),
        ("fleet_mix", "异构机队配比", "sensitivity_fleet_mix.png"),
    ]:
        path = outputs.get(key)
        if not path or not path.exists():
            continue
        df = pd.read_csv(path, encoding="utf-8-sig")
        if "完成率" not in df.columns:
            continue
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for alg, part in df.groupby("算法"):
            ax.plot(part[xcol].astype(str), part["完成率"].astype(float), marker="o", label=str(alg))
        ax.set_title(f"{xcol}敏感性：完成率")
        ax.set_xlabel(xcol)
        ax.set_ylabel("Completion rate")
        ax.legend()
        ax.tick_params(axis="x", rotation=20)
        fig.tight_layout()
        out = fig_dir / filename
        fig.savefig(out, dpi=160)
        plt.close(fig)
        made.append(out)
    return made


def _write_summary(preset: Dict[str, Any], raw_rows: List[Dict[str, Any]], outputs: Dict[str, Path], figures: List[Path], output_dir: Path) -> Path:
    ok_count = sum(1 for r in raw_rows if r["成功"])
    failures = [r for r in raw_rows if not r["成功"]]
    lines = [
        "# 一键实验摘要",
        "",
        f"- 预设：{preset.get('name', preset.get('_preset_key', 'unknown'))}",
        f"- 成功运行：{ok_count}/{len(raw_rows)}",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- 公平性：同一实验条件下不同算法使用相同 Seed。",
        "- 隔离性：每次运行使用独立 simulation.json 副本，未改写主配置。",
        "",
    ]
    alg = outputs.get("algorithm_comparison")
    if alg and alg.exists():
        import pandas as pd
        df = pd.read_csv(alg, encoding="utf-8-sig")
        lines += ["## 核心算法对比", ""]
        for _, r in df.iterrows():
            lines.append(
                f"- **{r['算法']}**：完成率 {float(r['完成率']):.2%}，超时率 {float(r['超时率']):.2%}，"
                f"无人机利用率 {float(r['无人机利用率']):.2%}，空载率 {float(r['空载率']):.2%}，"
                f"机巢周转率 {float(r['机巢周转率']):.4f}。"
            )
        lines.append("")
    paired_path = outputs.get("paired_ga_vs_greedy")
    if paired_path and paired_path.exists():
        import csv as _csv
        with open(paired_path, "r", encoding="utf-8-sig", newline="") as _f:
            _paired = list(_csv.DictReader(_f))
        lines += render_paired_markdown(_paired)
    lines += [
        "## 结果解释边界",
        "",
        "- `algorithm_comparison.csv` 是多次运行均值；`algorithm_comparison_stats.csv` 进一步给出标准差和中位数。",
        "- `paired_ga_vs_greedy.csv` 只比较相同 Seed 下的描述性差异，不替代统计显著性检验。",
        "- 若某指标不支持主推方案更优，应在结项报告中如实呈现，不应倒推结论。",
        "",
    ]
    if failures:
        lines += ["## 未完成的运行", ""]
        for r in failures[:20]:
            lines.append(f"- {r['实验']} / {r['取值']} / {r['算法']} / Seed {r['Seed']}：{r['错误']}")
        if len(failures) > 20:
            lines.append(f"- 另有 {len(failures)-20} 条失败记录，详见 raw_runs.csv。")
        lines.append("")
    lines += ["## 输出文件", ""]
    for k, p in outputs.items():
        try:
            rel = p.relative_to(output_dir)
        except ValueError:
            rel = p
        lines.append(f"- {k}: `{rel}`")
    for p in figures:
        lines.append(f"- figure: `{p.relative_to(output_dir)}`")
    path = output_dir / "summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_experiments(preset: Dict[str, Any], output_root: Path, status_file: Optional[Path] = None, dry_run: bool = False) -> Path:
    plan = build_plan(preset)
    if not plan:
        raise RuntimeError("预设没有启用任何实验")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = output_root / f"{preset.get('_preset_key', 'custom')}_{stamp}"

    base_cfg = json.loads(BASE_CONFIG.read_text(encoding="utf-8"))
    base = preset.get("base", {}) or {}
    episode_steps = int(base.get("episode_steps", base_cfg.get("environment", {}).get("episode_max_steps", 1200)))
    osm_path = Path(base.get("osm", DEFAULT_OSM))
    if not osm_path.is_absolute():
        osm_path = (PROJECT_ROOT / osm_path).resolve()

    status = {
        "state": "running" if not dry_run else "dry_run",
        "preset": preset.get("_preset_key", "custom"),
        "preset_name": preset.get("name", ""),
        "pid": os.getpid(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "total_runs": len(plan),
        "completed_runs": 0,
        "progress": 0.0,
        "current": "准备实验计划",
        "output_dir": "" if dry_run else str(output_dir),
        "error_count": 0,
    }
    _status_write(status_file, status)

    plan_rows = [{
        "序号": s.index, "实验": s.experiment, "变量": s.variable, "取值": s.value,
        "算法": s.algorithm, "重复": s.repeat, "Seed": s.seed, "配置补丁": json.dumps(s.patch, ensure_ascii=False),
    } for s in plan]
    if dry_run:
        # dry-run 的语义是“只看计划”。旧实现仍会创建 results/experiments/*
        # 目录和 plan.csv，容易让用户误以为实验已经执行，也会污染版本库。
        print(f"[dry-run] preset={preset.get('_preset_key', 'custom')}，runs={len(plan)}")
        for row in plan_rows:
            print(
                f"  #{row['序号']:>3} {row['实验']} / {row['变量']}={row['取值']} / "
                f"{row['算法']} / repeat={row['重复']} / seed={row['Seed']}"
            )
        status.update({"state": "completed", "completed_runs": 0, "progress": 1.0,
                       "current": "dry-run 完成", "finished_at": datetime.now().isoformat(timespec="seconds")})
        _status_write(status_file, status)
        return output_root / f"{preset.get('_preset_key', 'custom')}_dry-run"

    _preflight(plan, osm_path)

    # 只有真正开始实验后才创建结果目录。
    output_dir.mkdir(parents=True, exist_ok=True)
    config_dir = output_dir / "_run_configs"
    worker_dir = output_dir / "_worker_results"
    config_dir.mkdir(exist_ok=True)
    worker_dir.mkdir(exist_ok=True)
    resolved = copy.deepcopy(preset)
    resolved.pop("_preset_path", None)
    (output_dir / "experiment_config.yaml").write_text(
        yaml.safe_dump(resolved, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    _write_csv(output_dir / "plan.csv", plan_rows,
               ["序号", "实验", "变量", "取值", "算法", "重复", "Seed", "配置补丁"])
    manifest_path = write_manifest(
        output_dir=output_dir,
        project_root=PROJECT_ROOT,
        preset_path=Path(preset.get("_preset_path")) if preset.get("_preset_path") else None,
        base_config=BASE_CONFIG,
        algorithm_config=PROJECT_ROOT / "backend_si" / "config.yaml",
        osm_path=osm_path,
        plan_count=len(plan),
        algorithms=[s.algorithm for s in plan],
        preset_key=preset.get("_preset_key", "custom"),
    )

    raw_rows: List[Dict[str, Any]] = []
    for spec in plan:
        cfg = _deep_merge(copy.deepcopy(base_cfg), spec.patch)
        # 任务规模减小时，防止 initial_task_count 大于 total_tasks。
        real = cfg.get("task_generation", {}).get("realistic", {})
        if "total_tasks" in real and "initial_task_count" in real:
            real["initial_task_count"] = min(int(real["initial_task_count"]), int(real["total_tasks"]))
        cfg_path = config_dir / f"run_{spec.index:04d}.json"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        worker_out = worker_dir / f"run_{spec.index:04d}.json"

        status.update({
            "current": f"{spec.experiment} · {spec.value} · {ALGORITHM_LABELS.get(spec.algorithm, spec.algorithm)} · {spec.repeat}",
            "completed_runs": spec.index - 1,
            "progress": round((spec.index - 1) / len(plan), 6),
        })
        _status_write(status_file, status)
        print(f"[{spec.index}/{len(plan)}] {status['current']} (seed={spec.seed})")

        cmd = [
            sys.executable, "-m", "experiments.worker",
            "--config", str(cfg_path),
            "--algorithm", spec.algorithm,
            "--seed", str(spec.seed),
            "--episode-steps", str(episode_steps),
            "--osm", str(osm_path),
            "--output", str(worker_out),
        ]
        started = time.perf_counter()
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True)
        duration = time.perf_counter() - started
        if worker_out.exists():
            result = json.loads(worker_out.read_text(encoding="utf-8"))
        else:
            result = {"ok": False, "error": f"worker 未生成结果文件，exit={proc.returncode}", "metrics": {}}
        metrics = result.get("metrics", {}) or {}
        row = {
            "实验": spec.experiment,
            "变量": spec.variable,
            "取值": spec.value,
            "重复": spec.repeat,
            "Seed": spec.seed,
            "算法key": spec.algorithm,
            "算法": ALGORITHM_LABELS.get(spec.algorithm, spec.algorithm),
            "成功": bool(result.get("ok")),
            "耗时秒": round(float(result.get("duration_seconds", duration)), 4),
            "错误": result.get("error", ""),
        }
        row.update({c: float(metrics.get(c, 0.0)) for c in METRIC_COLUMNS})
        raw_rows.append(row)
        status["completed_runs"] = spec.index
        status["progress"] = round(spec.index / len(plan), 6)
        status["error_count"] = sum(1 for r in raw_rows if not r["成功"])
        _status_write(status_file, status)

    outputs = _aggregate(raw_rows, output_dir)
    outputs["reproducibility"] = manifest_path
    figures = _plot(outputs, output_dir)
    summary = _write_summary(preset, raw_rows, outputs, figures, output_dir)
    status.update({
        "state": "completed_with_errors" if status["error_count"] else "completed",
        "current": "实验完成",
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "summary": str(summary),
        "progress": 1.0,
    })
    _status_write(status_file, status)
    print(f"完成：{output_dir}")
    return output_dir


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="群智优衡：一键结项实验")
    parser.add_argument("--preset", default="conclusion", help="quick / conclusion / paper，或自定义 YAML 路径")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--status-file", default="")
    parser.add_argument("--dry-run", action="store_true", help="只打印实验计划，不创建结果目录、不运行仿真")
    args = parser.parse_args(argv)
    try:
        preset = load_preset(args.preset)
        status_file = Path(args.status_file).resolve() if args.status_file else None
        out = run_experiments(preset, Path(args.output_root).resolve(), status_file=status_file, dry_run=args.dry_run)
        print(f"output_dir={out}")
        return 0
    except Exception as exc:
        if args.status_file:
            status_path = Path(args.status_file).resolve()
            current = {}
            if status_path.exists():
                try:
                    current = json.loads(status_path.read_text(encoding="utf-8"))
                except Exception:
                    current = {}
            current.update({
                "state": "failed", "error": f"{type(exc).__name__}: {exc}",
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            })
            _status_write(status_path, current)
        print(f"实验启动失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
