"""Build a compact conclusion/defense evidence package.

The package is intentionally separate from the full source archive. It bundles the latest
formal experiment (when available), configs, key documentation and checksums so reviewers
can reproduce what was shown in the report/defense.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent
EXPERIMENT_ROOT = ROOT / "results" / "experiments"
DEFAULT_OUT = ROOT / "deliverables"

DOCS = [
    "README.md",
    "docs/算法口径说明.md",
    "docs/产品化收口与结项口径审计.md",
    "docs/交互式仿真与答辩演示.md",
    "docs/离线便携与端到端自检.md",
    "docs/结项修改说明.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "LICENSE",
    "requirements.txt",
    "VERSION",
]
CONFIGS = [
    "config/simulation.json",
    "backend_si/config.yaml",
    "experiments/presets/conclusion.yaml",
    "experiments/presets/quick.yaml",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_experiment(path: Path) -> None:
    required = ["summary.md", "raw_runs.csv", "experiment_config.yaml", "reproducibility.json"]
    missing = [name for name in required if not (path / name).exists()]
    if missing:
        raise RuntimeError(f"实验目录缺少 v1.0 正式证据文件: {', '.join(missing)}")
    with (path / "raw_runs.csv").open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError("raw_runs.csv 为空，不能作为正式结项证据")
    failed = [r for r in rows if str(r.get("成功", "")).strip().lower() not in {"true", "1", "yes"}]
    if failed:
        raise RuntimeError(f"正式实验含 {len(failed)} 条失败运行，请修复并重新运行 conclusion 后再归档")


def latest_conclusion_experiment() -> Optional[Path]:
    if not EXPERIMENT_ROOT.exists():
        return None
    candidates = sorted(
        [p for p in EXPERIMENT_ROOT.glob("conclusion_*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            _validate_experiment(path)
            return path
        except Exception:
            continue
    return None


def copy_tree_filtered(src: Path, dst: Path) -> None:
    ignore_names = {"_run_configs", "_worker_results", "__pycache__"}
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if any(part in ignore_names for part in rel.parts):
            continue
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def build(experiment: Optional[Path], output: Optional[Path], allow_missing: bool) -> Path:
    if experiment is None:
        experiment = latest_conclusion_experiment()
    if experiment is not None:
        experiment = experiment.resolve()
        if not experiment.exists():
            raise FileNotFoundError(f"实验目录不存在: {experiment}")
        _validate_experiment(experiment)
    elif not allow_missing:
        raise RuntimeError("未找到通过 v1.0 证据校验的 conclusion_* 正式实验。请先在完整环境运行 python run_conclusion.py --preset conclusion；若旧结果缺少 reproducibility.json，也需要重新运行。")

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else "unknown"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    DEFAULT_OUT.mkdir(parents=True, exist_ok=True)
    output = output or (DEFAULT_OUT / f"SwarmBalance-v{version}-结项证据包-{stamp}.zip")
    output = output.resolve()

    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / f"SwarmBalance-v{version}-结项证据包"
        stage.mkdir(parents=True)
        missing = []
        for rel in DOCS + CONFIGS:
            src = ROOT / rel
            if not src.exists():
                missing.append(rel)
                continue
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        # 白名单文件缺失必须中断：历史上文档整体移入 docs/ 后，这里静默跳过了
        # 5 份核心口径文档，结项包照常生成、返回码为 0，抽检才发现内容不全。
        if missing:
            raise FileNotFoundError(
                "结项证据包白名单文件缺失，已中断打包：%s。"
                "若文件被移动或改名，请同步更新 build_conclusion_package.py 的 DOCS/CONFIGS。"
                % "、".join(missing)
            )
        if experiment is not None:
            copy_tree_filtered(experiment, stage / "正式实验结果" / experiment.name)

        note = [
            "# SwarmBalance 结项交付证据包",
            "",
            f"- 项目版本：{version}",
            f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 正式实验：{experiment.name if experiment else '未包含（当前仅生成结构检查包）'}",
            "",
            "## 使用原则",
            "",
            "- `正式实验结果/` 中的数据才可用于论文/结项报告的定量结果。",
            "- `reproducibility.json`（若实验已生成）记录运行环境、输入文件哈希和包版本。",
            "- `paired_ga_vs_greedy.csv` 是相同 Seed 的描述性配对比较，不代表统计显著性。",
            "- 完整源代码请使用同版本项目源码包；本包用于证据归档与复现说明。",
            "",
        ]
        (stage / "结项交付说明.md").write_text("\n".join(note), encoding="utf-8")

        checks = []
        for p in sorted(stage.rglob("*")):
            if p.is_file() and p.name != "CHECKSUMS.sha256":
                checks.append(f"{sha256(p)}  {p.relative_to(stage).as_posix()}")
        (stage / "CHECKSUMS.sha256").write_text("\n".join(checks) + "\n", encoding="utf-8")

        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for p in sorted(stage.rglob("*")):
                if p.is_file():
                    zf.write(p, p.relative_to(stage.parent))
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="构建 SwarmBalance 结项证据包")
    parser.add_argument("--experiment-dir", default="", help="指定 conclusion_* 实验目录；默认取最新")
    parser.add_argument("--output", default="")
    parser.add_argument("--allow-missing-experiment", action="store_true", help="没有正式实验时也生成结构检查包")
    args = parser.parse_args(argv)
    exp = Path(args.experiment_dir) if args.experiment_dir else None
    out = Path(args.output) if args.output else None
    try:
        path = build(exp, out, allow_missing=args.allow_missing_experiment)
        print(f"package={path}")
        return 0
    except Exception as exc:
        print(f"构建失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
