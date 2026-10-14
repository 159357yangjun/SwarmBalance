#!/usr/bin/env python3
"""TaskUI 1.0 manifest linter — stdlib only. Never claims runtime UX verification."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

VERSION = "1.0"
PATTERNS = {"content-editor", "object-management", "business-workflow", "monitoring-analysis", "guided-wizard"}
PLATFORMS = {"web", "desktop", "touch"}
FREQUENCIES = {"high", "medium", "low"}
RISKS = {"low", "medium", "high"}
SCOPES = {"global", "workspace", "object"}
EFFECTS = {"read", "mutate", "destructive"}
ROLES = {"primary", "navigation", "toolbar", "inspector", "preview", "status", "secondary", "log", "filter"}
SURFACES = {"toolbar", "inline", "menu", "context-menu", "shortcut", "command-palette", "inspector", "dialog", "navigation", "settings"}
RECOVERY = {"undo", "soft-delete", "version-restore", "transaction-rollback", "retry", "cancel", "not-needed", "none"}
SAFE_RECOVERY = {"undo", "soft-delete", "version-restore", "transaction-rollback"}


def is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_int(value: Any) -> bool:
    return type(value) is int


def is_num(value: Any) -> bool:
    return type(value) in (int, float)


def is_choice(value: Any, choices: set[str]) -> bool:
    return isinstance(value, str) and value in choices


class Checker:
    def __init__(self, manifest: Any, manifest_path: Path):
        self.doc = manifest
        self.path = manifest_path
        self.diagnostics: list[dict[str, str]] = []

    def add(self, severity: str, code: str, pointer: str, message: str) -> None:
        self.diagnostics.append({"severity": severity, "code": code, "path": pointer, "message": message})

    def error(self, code: str, pointer: str, message: str) -> None:
        self.add("error", code, pointer, message)

    def warn(self, code: str, pointer: str, message: str) -> None:
        self.add("warning", code, pointer, message)

    def array(self, obj: dict, field: str, pointer: str, required: bool = True) -> list:
        value = obj.get(field)
        if not isinstance(value, list):
            if required or value is not None:
                self.error("E001", f"{pointer}/{field}", "必须是数组")
            return []
        return value

    def require_string(self, obj: dict, field: str, pointer: str) -> str:
        value = obj.get(field)
        if not is_text(value):
            self.error("E002", f"{pointer}/{field}", "必须是非空字符串")
            return ""
        return value.strip()

    def unique_ids(self, items: list, pointer: str, prefix: str) -> dict[str, dict]:
        seen = {}
        for i, item in enumerate(items):
            p = f"{pointer}/{i}"
            if not isinstance(item, dict):
                self.error("E003", p, "必须是对象")
                continue
            ident = self.require_string(item, "id", p)
            if not ident:
                continue
            if ident in seen:
                self.error("E010", f"{p}/id", f"重复的 {prefix} ID：{ident}")
            else:
                seen[ident] = item
        return seen

    def run(self) -> list[dict[str, str]]:
        d = self.doc
        if not isinstance(d, dict):
            self.error("E000", "/", "manifest 顶层必须是 JSON 对象")
            return self.diagnostics
        if d.get("version") != VERSION:
            self.error("E011", "/version", f"仅支持版本 {VERSION}")

        project = d.get("project")
        if not isinstance(project, dict):
            self.error("E012", "/project", "缺少 project 对象")
            project = {}
        self.require_string(project, "name", "/project")
        self.require_string(project, "primary_user", "/project")
        platform = project.get("platform")
        if not is_choice(platform, PLATFORMS):
            self.error("E013", "/project/platform", f"platform 必须为 {sorted(PLATFORMS)} 之一")
        patterns = self.array(project, "patterns", "/project")
        if not patterns or any(p not in PATTERNS for p in patterns if isinstance(p, str)) or any(not isinstance(p, str) for p in patterns):
            self.error("E014", "/project/patterns", f"至少选择一个有效模式：{sorted(PATTERNS)}")
        if len(patterns) != len(set(str(p) for p in patterns)):
            self.warn("W014", "/project/patterns", "存在重复模式")

        tasks_list = self.array(d, "tasks", "")
        screens_list = self.array(d, "screens", "")
        actions_list = self.array(d, "actions", "")
        for key, arr in (("tasks", tasks_list), ("screens", screens_list), ("actions", actions_list)):
            if not arr:
                self.error("E015", f"/{key}", f"{key} 不能为空")
        tasks = self.unique_ids(tasks_list, "/tasks", "task")
        screens = self.unique_ids(screens_list, "/screens", "screen")
        actions = self.unique_ids(actions_list, "/actions", "action")

        screen_regions: dict[str, set[str]] = {}
        toolbar_counts: Counter[str] = Counter()
        for idx, s in enumerate(screens_list):
            if not isinstance(s, dict):
                continue
            p = f"/screens/{idx}"
            self.require_string(s, "name", p)
            sid = s.get("id", "")
            regions = self.array(s, "regions", p)
            region_objs = self.unique_ids(regions, f"{p}/regions", "region")
            if is_text(sid):
                screen_regions[sid] = set(region_objs)
            primary_regions = [r.get("id") for r in regions if isinstance(r, dict) and r.get("role") == "primary"]
            if len(primary_regions) != 1:
                self.error("E210", f"{p}/regions", "工作区必须且只能声明一个 primary 角色区域")
            if s.get("primary_region") not in primary_regions:
                self.error("E211", f"{p}/primary_region", "primary_region 必须指向角色为 primary 的区域")
            ratio = s.get("main_region_min_ratio")
            if not is_num(ratio) or not (0 < ratio <= 1):
                self.error("E212", f"{p}/main_region_min_ratio", "必须声明 0～1 的主工作区最低占比目标（不等于实测值）")
            elif ratio < 0.5:
                self.warn("W212", f"{p}/main_region_min_ratio", "主工作区目标占比低于 50%；请在决策记录中解释")
            persistent = 0
            for ri, r in enumerate(regions):
                if not isinstance(r, dict):
                    continue
                role = r.get("role")
                if not is_choice(role, ROLES):
                    self.error("E213", f"{p}/regions/{ri}/role", f"区域 role 必须为 {sorted(ROLES)} 之一")
                if type(r.get("persistent")) is not bool:
                    self.error("E214", f"{p}/regions/{ri}/persistent", "persistent 必须是布尔值")
                if r.get("persistent") is True:
                    persistent += 1
            if persistent > 5:
                self.warn("W215", f"{p}/regions", f"存在 {persistent} 个常驻区域，检查是否拥挤（启发式提醒）")

        for idx, t in enumerate(tasks_list):
            if not isinstance(t, dict):
                continue
            p = f"/tasks/{idx}"
            self.require_string(t, "name", p)
            self.require_string(t, "success_criterion", p)
            if not is_choice(t.get("frequency"), FREQUENCIES):
                self.error("E110", f"{p}/frequency", "频率必须为 high/medium/low")
            steps = self.array(t, "steps", p)
            budget = t.get("step_budget")
            if not is_int(budget) or budget < 1:
                self.error("E111", f"{p}/step_budget", "必须是 >= 1 的整数")
            elif len(steps) > budget:
                self.error("E112", f"{p}/steps", f"声明的 {len(steps)} 个步骤超过任务预算 {budget}；需调整任务路径或解释预算")
            if not steps:
                self.error("E113", f"{p}/steps", "任务必须有至少一个操作步骤")
            for j, step in enumerate(steps):
                if not isinstance(step, str) or step not in actions:
                    self.error("E114", f"{p}/steps/{j}", f"步骤 {step!r} 未指向有效 action ID")
                elif not isinstance(actions[step].get("task_ids"), list) or t.get("id") not in actions[step]["task_ids"]:
                    self.error("E115", f"{p}/steps/{j}", f"操作 {step} 必须反向关联任务 {t.get('id')}")

        for idx, a in enumerate(actions_list):
            if not isinstance(a, dict):
                continue
            p = f"/actions/{idx}"
            aid = a.get("id")
            self.require_string(a, "name", p)
            for field, allowed in (("scope", SCOPES), ("frequency", FREQUENCIES), ("risk", RISKS), ("effect", EFFECTS), ("recovery", RECOVERY)):
                if not is_choice(a.get(field), allowed):
                    self.error("E300", f"{p}/{field}", f"{field} 必须属于 {sorted(allowed)}")
            linked = self.array(a, "task_ids", p)
            if not linked:
                self.warn("W301", f"{p}/task_ids", "该操作未关联用户任务；检查是否展示型冗余功能")
            for j, tid in enumerate(linked):
                if not isinstance(tid, str) or tid not in tasks:
                    self.error("E302", f"{p}/task_ids/{j}", f"未知任务 {tid!r}")
            entrypoints = self.array(a, "entrypoints", p)
            if not entrypoints:
                self.error("E310", f"{p}/entrypoints", "操作缺少入口")
            accessible = False
            shortcut = False
            for j, ep in enumerate(entrypoints):
                ep_p = f"{p}/entrypoints/{j}"
                if not isinstance(ep, dict):
                    self.error("E311", ep_p, "入口必须是对象")
                    continue
                sid, rid = ep.get("screen_id"), ep.get("region_id")
                surface = ep.get("surface")
                depth = ep.get("menu_depth")
                if not isinstance(sid, str) or sid not in screens:
                    self.error("E312", f"{ep_p}/screen_id", f"未知屏幕 {sid!r}")
                elif not isinstance(rid, str) or rid not in screen_regions.get(sid, set()):
                    self.error("E313", f"{ep_p}/region_id", f"屏幕 {sid} 不存在区域 {rid!r}")
                if not is_choice(surface, SURFACES):
                    self.error("E314", f"{ep_p}/surface", f"surface 必须属于 {sorted(SURFACES)}")
                if not is_int(depth) or depth < 0:
                    self.error("E315", f"{ep_p}/menu_depth", "menu_depth 必须是非负整数")
                if is_choice(surface, {"menu", "context-menu"}) and is_int(depth) and depth > 3:
                    self.warn("W316", f"{ep_p}/menu_depth", "菜单嵌套超过 3 层，需检查发现成本")
                if a.get("scope") == "object" and not is_text(ep.get("context")):
                    self.warn("W317", f"{ep_p}/context", "对象级功能应标明出现条件/选中状态")
                if surface == "shortcut":
                    shortcut = True
                if is_choice(surface, {"inline", "toolbar", "shortcut", "context-menu", "command-palette", "inspector"}) or (surface == "menu" and is_int(depth) and depth <= 1):
                    accessible = True
                if surface == "toolbar" and isinstance(sid, str) and sid in screens:
                    toolbar_counts[sid] += 1
            if a.get("frequency") == "high" and not accessible:
                self.warn("W320", p, "高频操作只声明了深层/非直接入口；应说明为什么不能在当前上下文便捷访问")
            if a.get("frequency") == "high" and is_choice(a.get("effect"), {"mutate", "destructive"}) and is_choice(platform, {"desktop", "web"}) and not shortcut:
                self.warn("W321", p, "高频修改操作未声明快捷键；评估是否适用（不是强制必须有）")
            if a.get("risk") == "high" and not is_choice(a.get("recovery"), SAFE_RECOVERY) and not is_text(a.get("confirmation")):
                self.error("E330", p, "高风险操作既无可信恢复手段也无明确确认机制")
            if is_choice(a.get("effect"), {"mutate", "destructive"}):
                fb = self.array(a, "feedback", p)
                if not {"success", "failure"}.issubset(set(str(v) for v in fb)):
                    self.error("E331", f"{p}/feedback", "修改类操作至少需要声明 success 与 failure 状态")
            if is_text(aid) and linked and not any(aid in t.get("steps", []) for t in tasks_list if isinstance(t, dict) and isinstance(t.get("steps"), list)):
                self.warn("W332", p, "该操作有关联任务，但没有出现在任何任务操作路径中")

        for sid, count in toolbar_counts.items():
            if count > 8:
                self.warn("W340", f"/screens/{sid}", f"常驻 toolbar 操作入口达 {count} 项，可能拥挤；需结合界面实测")

        evidence = d.get("design_evidence")
        if not isinstance(evidence, dict):
            self.error("E400", "/design_evidence", "必须提供设计证据对象")
            evidence = {}
        for field in ("wireframe", "task_walkthrough", "decision_log"):
            rel = self.require_string(evidence, field, "/design_evidence")
            if rel and not (self.path.parent / rel).is_file():
                self.error("E401", f"/design_evidence/{field}", f"文件不存在：{rel}（相对清单所在目录）")

        plan = d.get("test_plan")
        if not isinstance(plan, dict):
            self.error("E410", "/test_plan", "缺少 test_plan 对象；静态检查不代替真实测试")
        else:
            viewports = self.array(plan, "viewport_sizes", "/test_plan")
            if not viewports or any(not is_text(v) for v in viewports):
                self.error("E411", "/test_plan/viewport_sizes", "至少声明一个待实际测试的目标窗口尺寸")
            covered = self.array(plan, "covered_tasks", "/test_plan")
            for ti, tid in enumerate(covered):
                if not isinstance(tid, str) or tid not in tasks:
                    self.error("E412", f"/test_plan/covered_tasks/{ti}", f"未知任务：{tid!r}")
            missing = {tid for tid, t in tasks.items() if t.get("frequency") == "high"} - set(str(t) for t in covered)
            if missing:
                self.error("E413", "/test_plan/covered_tasks", f"高频任务没有安排实际测试：{sorted(missing)}")
            if not is_choice(plan.get("status"), {"planned", "in-progress", "verified"}):
                self.error("E414", "/test_plan/status", "必须是 planned / in-progress / verified")

        return self.diagnostics


def check(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "file": str(path), "summary": {"errors": 1, "warnings": 0}, "diagnostics": [
            {"severity": "error", "code": "EJSON", "path": "/", "message": str(exc)}
        ], "note": "只能证明清单结构与启发式规则；不等于实际界面通过可用性测试"}
    checker = Checker(doc, path)
    diagnostics = checker.run()
    diagnostics.sort(key=lambda item: (item["severity"] != "error", item["code"], item["path"]))
    errors = sum(1 for item in diagnostics if item["severity"] == "error")
    warnings = len(diagnostics) - errors
    return {"ok": errors == 0, "file": str(path), "summary": {"errors": errors, "warnings": warnings},
            "diagnostics": diagnostics, "note": "静态清单检查通过不等于 UI 已实现、好用或通过可用性测试"}


def main() -> int:
    parser = argparse.ArgumentParser(description="TaskUI manifest 静态一致性检查（不验证实际 UI）")
    parser.add_argument("manifest", type=Path, help="project.taskui.json 文件路径")
    parser.add_argument("--strict", action="store_true", help="将启发式警告也视为不通过")
    parser.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    args = parser.parse_args()
    result = check(args.manifest)
    failed = result["summary"]["errors"] > 0 or (args.strict and result["summary"]["warnings"] > 0)
    if args.json:
        print(json.dumps({**result, "pass": not failed}, ensure_ascii=False, indent=2))
    else:
        for d in result["diagnostics"]:
            print(f"{d['severity'].upper():7} {d['code']} {d['path']}: {d['message']}")
        print(f"{'FAIL' if failed else 'PASS'}: errors={result['summary']['errors']} warnings={result['summary']['warnings']}")
        print(result["note"])
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
