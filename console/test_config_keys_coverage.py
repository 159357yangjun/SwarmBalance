# -*- coding: utf-8 -*-
"""配置键覆盖率门禁 —— 由 `python -m unittest discover -s console` 自动收集。

要治的病：模块被删掉之后，它在配置文件里留下的键没人读、也没人发现。
第一个案例是 `config/simulation.json` 的 metrics 段：那里写的键名与读它的一侧
（`frontend/evaluate_metrics.py:92` 拼的是 f"{policy}_file"）对不上，
改这些键完全无效却无人报警。当时那段有几个键、其中几个是哑的，不抄在这里
（当场数：`python -c "import json;print(len(json.load(open('config/simulation.json',encoding='utf-8'))['metrics']))"`
—— `encoding` 那个参数在本机是承重的：默认 GBK 读这份带中文注释的 JSON 会直接 UnicodeDecodeError。）
那四个对不上名字的键是哪一轮清掉的不写在这里，
`git log -p -- config/simulation.json` 一次就能追到。

判定方式：把全部源码里的**字符串字面量**收成一个集合，配置叶子键若不在其中，
就是"改了不起作用"的哑键。这个判据偏保守 —— 只要键名以任何形式出现在代码里就算通过，
所以像 enabled / type / radius 这类常见词几乎必然"通过"。这是有意的：
本测试的职责是抓遗留哑键，宁可漏报也不误报，否则会被当成噪声关掉。

动态拼出来的键（f"{x}_file" 这类）字面量不存在，会被误判为哑键 —— 这类键必须写进
ALLOWED_UNREAD，并附理由与真正的读取位置。白名单是强制自证的：没有 reason 直接失败。
"""
from __future__ import annotations

import io
import json
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 受检配置文件。config/positions.json 是纯坐标数组、无命名键，不在此列。
CONFIG_FILES = [
    "config/simulation.json",
    "backend_si/config.yaml",
    "experiments/presets/conclusion.yaml",
    "experiments/presets/paper.yaml",
    "experiments/presets/quick.yaml",
]

# 扫描源码的扩展名与排除目录
SRC_EXT = {".py", ".html", ".js", ".bat", ".ps1"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv310", ".idea",
             ".osm_cache", "data", "results", "deliverables", "paper", "docs"}

# 允许"代码里查不到字面量"的键：必须写 reason，且 reason 里要点明真正的读取位置。
# 结构：{dotted_path_or_key: reason}
ALLOWED_UNREAD = {
    "heterogeneous.drone_types.light_express.full_load_range_km":
        "仅展示值：README 机型表「满载续航 (km)」列的产品规格（美团第四代 10 km）。"
        "仿真里的续航不是读这个键，而是由 battery_capacity × battery_consumption_base × "
        "battery_load_penalty_factor 在 frontend/drone.py 的耗电模型算出。改此键不改变任何仿真结果。",
    "heterogeneous.drone_types.standard_cargo.full_load_range_km":
        "仅展示值：README 机型表「满载续航 (km)」列的产品规格（丰翼 ARK40 20 km）。"
        "仿真续航同上由 battery_capacity 与放电模型推导，不读此键。",
    "heterogeneous.drone_types.heavy_cargo.full_load_range_km":
        "仅展示值：README 机型表「满载续航 (km)」列的产品规格（大疆 FlyCart 30 双电 16 km）。"
        "仿真续航同上由 battery_capacity 与放电模型推导，不读此键。",
}

_LITERAL = re.compile(r"""['"]([^'"\n\\]{1,64})['"]""")


def _code_string_literals() -> set:
    out = set()
    here = os.path.realpath(__file__)
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if os.path.splitext(fn)[1].lower() not in SRC_EXT:
                continue
            full = os.path.join(dirpath, fn)
            # 本文件自身必须排除：否则"在门禁源码里写出键名"就等于"该键被读取"，
            # 门禁可以自证通过，检查就废了。
            if os.path.realpath(full) == here:
                continue
            try:
                with io.open(full, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            out.update(_LITERAL.findall(text))
    return out


def _leaf_paths(node, prefix=""):
    """yield (dotted_path, leaf_key) for every named leaf."""
    if isinstance(node, dict):
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict) and v:
                yield from _leaf_paths(v, path)
            elif isinstance(v, list) and v and isinstance(v[0], (dict, list)):
                for item in v:
                    yield from _leaf_paths(item, path + "[]")
            else:
                yield path, str(k)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)):
                yield from _leaf_paths(item, prefix + "[]")


def _load(rel: str):
    p = ROOT / rel
    if not p.is_file():
        return None
    if rel.endswith(".json"):
        return json.loads(p.read_text(encoding="utf-8"))
    try:
        import yaml
    except ImportError:            # 裸解释器没装 PyYAML 时跳过 YAML，不失败
        return None
    return yaml.safe_load(p.read_text(encoding="utf-8"))


# 变异探针：这个字面量**只出现在本文件里**。它唯一的用途，是让"语料集排除门禁自身"
# 这条逻辑被改坏时立刻有测试失败。否则门禁可以自证通过 —— 在自身源码里写出某个键名
# 就等于"该键已被代码读取"，而这种失效是静默的：测试会变绿而不是变红。
# 不要删除它，也不要在别的文件里引用它。
_SELF_EXCLUSION_PROBE = "zz_self_exclusion_probe_marker_only_in_gate_file"


class ConfigKeyCoverageTests(unittest.TestCase):
    """每个配置叶子键都必须至少被代码读取一次，否则视为遗留哑键。"""

    @classmethod
    def setUpClass(cls):
        cls.literals = _code_string_literals()

    def test_gate_corpus_excludes_the_gate_itself(self):
        """变异测试：把 _code_string_literals 里排除自身那行删掉或写反，本条必须失败。"""
        with io.open(__file__, encoding="utf-8", errors="replace") as fh:
            own = fh.read()
        self.assertIn(_SELF_EXCLUSION_PROBE, own,
                      "探针字面量必须真实存在于本文件，否则这条变异测试是空转")
        # 用 assertFalse 而不是 assertNotIn：后者的默认消息是
        # "'x' unexpectedly found in {整个容器}"，会把上万个字面量全打出来（实测 158KB）。
        self.assertFalse(
            _SELF_EXCLUSION_PROBE in self.literals,
            "门禁自身源码的字面量进入了语料集 —— 说明语料集没有排除本文件。"
            "那样只要在门禁代码里写出某个键名，就会被当成「该键已被代码读取」，"
            "门禁可自证通过，哑键检查静默失效。"
            "（语料集当前含 %d 个字面量，不在此打印）" % len(self.literals))

    def test_every_config_leaf_key_is_read_somewhere(self):
        orphans, stale_allow = [], []
        seen_allow = set()
        checked = 0

        for rel in CONFIG_FILES:
            data = _load(rel)
            if data is None:
                continue
            for dotted, key in _leaf_paths(data):
                checked += 1
                if key in self.literals:
                    continue
                if dotted in ALLOWED_UNREAD:
                    seen_allow.add(dotted)
                    continue
                orphans.append("%s:%s" % (rel, dotted))

        # 白名单里已经不存在的键也要报，否则白名单会越积越脏
        for dotted in ALLOWED_UNREAD:
            if dotted not in seen_allow:
                stale_allow.append(dotted)

        self.assertGreater(checked, 100,
                           "只检查到 %d 个键，扫描逻辑可能失效了（宁可报错也不静默通过）" % checked)

        msgs = []
        if orphans:
            msgs.append(
                "\n发现 %d 个「改了不起作用」的哑键（代码里查不到该键名字面量）：\n  %s\n"
                "若该键确实只是展示值，请写进 console/test_config_keys_coverage.py 的 "
                "ALLOWED_UNREAD 并在 reason 里注明它出现在哪份文档；"
                "若是遗留物（模块已删/机制已被取代），请连同配置一起删除。"
                % (len(orphans), "\n  ".join(orphans)))
        if stale_allow:
            msgs.append("\nALLOWED_UNREAD 里有 %d 条已失效（对应键在配置中已不存在或已被代码读取）："
                        "\n  %s" % (len(stale_allow), "\n  ".join(stale_allow)))
        if msgs:
            self.fail("".join(msgs))

    def test_allowlist_entries_carry_a_reason(self):
        for dotted, reason in ALLOWED_UNREAD.items():
            self.assertTrue(
                isinstance(reason, str) and len(reason.strip()) >= 12,
                "白名单条目 %s 的 reason 太短，必须写清它为什么允许无人读取" % dotted)

    def test_scanner_actually_detects_a_planted_orphan(self):
        """防止扫描器本身变成哑门禁：造一个假键，必须被判为未覆盖。

        键名在运行时拼接，避免它作为字面量出现在本文件里而被语料集收录。
        """
        planted = "zz" + "_planted_" + "orphan" + "_key"
        fake = {"a": {"b": {planted: 1}}}
        found = list(_leaf_paths(fake))
        self.assertEqual(found, [("a.b." + planted, planted)])
        self.assertNotIn(planted, self.literals,
                         "探针键不该出现在真实代码里；若出现说明语料集把测试自身也算进去了")
        self.assertNotIn("a.b." + planted, ALLOWED_UNREAD,
                         "探针键不该在白名单里")


if __name__ == "__main__":
    unittest.main()
