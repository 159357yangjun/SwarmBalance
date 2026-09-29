# -*- coding: utf-8 -*-
"""加载路径基线门禁必须真的能阻断 —— 把上一轮手工做的验证固化成用例。

为什么这条测试值得存在：旧版 check_loader 只比较 fallback 与当前路径的碰撞体数是否相等。
osmnx 整个消失时两条路径都退化成 fallback、数值都是 108、相等 → 返回 0 通过。
也就是说**最可能发生的那种环境变化，恰好是旧门禁唯一看不见的情况**。

设计上的一个坑（本文件第一版就中了）：不能只依赖"当前机器 osmnx 是否可用"来决定跑不跑。
console/test_environment_incidents.py 会往 sys.modules 里塞一个假 osmnx，
在 `discover -s console` 的全量跑里它会先执行，于是本类的 setUp 会判定"不可用"而
skipTest —— 门禁在最需要它的聚合跑里静默不执行。因此核心那条改成**契约测试**：
直接喂一个合成观测值给判定逻辑，与机器状态无关、必然执行。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "frontend")):
    if p not in sys.path:
        sys.path.insert(0, p)

import verify_data_provenance as V  # noqa: E402

BASELINE = json.loads((ROOT / "provenance_baseline.json").read_text(encoding="utf-8"))


def _obs(mode, osmnx_colliders, fallback_colliders=108):
    """构造一个合成观测，形状与 _loader_observation() 的返回一致。"""
    paths = {
        "fallback": {"buildings": 2876, "height_is_none": 2479, "height_is_nan": 0,
                     "finite_heights": 397, "colliders_gt_20m": fallback_colliders},
        "osmnx": {"buildings": 2889, "height_is_none": 0, "height_is_nan": 2864,
                  "finite_heights": 25, "colliders_gt_20m": osmnx_colliders},
    }
    # 当前路径 = 该 mode 实际会用的那份数据
    paths["osmnx"] = dict(paths["osmnx"]) if mode == "osmnx" else dict(paths["fallback"])
    return {"mode": mode, "paths": {"fallback": paths["fallback"],
                                    "osmnx": paths["osmnx"] if mode == "osmnx"
                                    else paths["fallback"]}}


class LoaderBaselineContractTests(unittest.TestCase):
    """判定逻辑的契约：与基线不符就必须非零，且不依赖本机装了哪些包。"""

    def _run_with(self, obs, allow_drift=False):
        report = []
        original = V._loader_observation
        V._loader_observation = lambda: (obs, None)
        try:
            rc = V.check_loader(report, allow_drift=allow_drift)
        finally:
            V._loader_observation = original
        return rc, report

    def test_osmnx_gone_but_paths_equal_still_blocks(self):
        """旧逻辑被骗过的确切形状：两条路径都是 108 且相等，但 mode 已与基线不符。"""
        rc, report = self._run_with(_obs("fallback", 108))
        self.assertEqual(rc, 1, "osmnx 消失必须阻断；旧实现在这里返回 0")
        fails = [m for s, _, m in report if s == "FAIL"]
        self.assertTrue(any("不一致" in m for m in fails),
                        "要报出漂移条目，实际 FAIL=%s" % fails)
        self.assertTrue(any("mode=fallback" in m for m in fails),
                        "漂移原因里必须点出 mode 变了，实际=%s" % fails)

    def test_matching_baseline_does_not_block(self):
        """反面对照：与基线一致时不许报 FAIL，否则门禁会退化成永远红。"""
        rc, report = self._run_with(_obs(BASELINE["expected_mode"],
                                         BASELINE["paths"]["osmnx"]["colliders_gt_20m"]))
        self.assertEqual(rc, 0, "与基线一致却被阻断：%s" % [m for s, _, m in report if s == "FAIL"])
        self.assertTrue(any(s == "OK" for s, _, _ in report), "应有一条 OK 说明一致")

    def test_collider_count_drift_detected_even_with_same_mode(self):
        rc, _ = self._run_with(_obs(BASELINE["expected_mode"], 7))
        self.assertEqual(rc, 1, "碰撞体数变了但 mode 没变，也必须被发现")

    def test_allow_drift_downgrades_to_warn_not_silence(self):
        rc, report = self._run_with(_obs("fallback", 108), allow_drift=True)
        self.assertEqual(rc, 0, "显式放行时不再阻断")
        self.assertTrue(any(s == "WARN" for s, _, _ in report),
                        "放行必须留 WARN，不能变成静默通过")

    def test_missing_baseline_file_blocks(self):
        """基线文件丢了不能当作"没变化"。

        探针必须自己证明生效：check_loader 用 os.path.isfile(字符串) 判断存在性，
        第一版这里改的是 Path.is_file，打在了另一个入口上 → 门禁照旧读到真基线、返回 0，
        断言变成空转。现在改成把 ROOT 指向空目录，并显式确认基线在那个 ROOT 下不存在。
        """
        report = []
        original_obs = V._loader_observation
        original_root = V.ROOT
        with tempfile.TemporaryDirectory() as tmp:
            V._loader_observation = lambda: (_obs("osmnx", 18), None)
            V.ROOT = tmp
            try:
                self.assertFalse(
                    os.path.isfile(os.path.join(V.ROOT, "provenance_baseline.json")),
                    "探针没生效：临时 ROOT 下已经存在基线文件，后面的断言就是空转")
                rc = V.check_loader(report, allow_drift=False)
            finally:
                V.ROOT = original_root
                V._loader_observation = original_obs
        self.assertEqual(rc, 1, "缺基线文件必须失败，不能默认通过")
        self.assertTrue(any("缺基线" in m for s, _, m in report if s == "FAIL"),
                        "要报出缺基线，实际=%s" % [(s, m) for s, _, m in report])

    def test_baseline_is_machine_readable_and_complete(self):
        for key in ("expected_mode", "paths"):
            self.assertIn(key, BASELINE)
        for name in ("osmnx", "fallback"):
            self.assertIn(name, BASELINE["paths"])
            for field in ("buildings", "height_is_none", "height_is_nan", "colliders_gt_20m"):
                self.assertIsInstance(BASELINE["paths"][name].get(field), int,
                                      "基线缺字段 %s.%s" % (name, field))


class LoaderBaselineLiveTests(unittest.TestCase):
    """真实环境 + 真实探针的两条。

    写成这样而不是"读当前 sys.modules 里的 osmnx"，原因在文件头：全量 discover 里
    console/test_environment_incidents.py 会先注入一个假 osmnx，若本类据此决定跑不跑，
    门禁就在最需要它的聚合跑里静默 skip。这里自己装配 ox 模块、并用子进程读真实环境，
    两者都不受进程内污染影响。
    """

    def _with_fake_osmnx(self, with_attrs):
        """临时把 osm 模块的 ox 换成可控桩，返回 _osmnx_available() 的判定。"""
        import types

        try:
            from tools import osm as osm_mod
        except Exception as exc:
            self.skipTest("tools.osm 导入失败（缺 numpy 等）：%s" % exc)
        stub = types.ModuleType("osmnx")
        if with_attrs:
            stub.graph_from_xml = lambda *a, **k: None
            stub.features_from_xml = lambda *a, **k: None
        saved = osm_mod.ox
        osm_mod.ox = stub
        try:
            return osm_mod._osmnx_available()
        finally:
            osm_mod.ox = saved

    def test_probe_detects_missing_attributes_not_just_module_presence(self):
        """探针判的是"有没有用到的入口"，不是"模块对象是不是 None"。

        若有人把 _osmnx_available 简化回 `ox is not None`，一个残缺的 osmnx 会被判可用，
        然后 load_map_data 里 AttributeError —— 这条用例就是那个简化的反例。
        """
        self.assertTrue(self._with_fake_osmnx(True))
        self.assertFalse(self._with_fake_osmnx(False),
                         "空壳 osmnx 必须判为不可用，否则 osm.py:37 的判据已被改弱")

    def test_real_environment_matches_baseline(self):
        """子进程跑真实 --loader：干净解释器里必须 exit 0，且实测值等于基线。"""
        proc = subprocess.run(
            [sys.executable, str(ROOT / "verify_data_provenance.py"), "--loader"],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        out = proc.stdout + proc.stderr
        self.assertNotIn("Traceback", out, "子进程崩了却仍被判过：\n%s" % out[-1500:])
        if "No module named" in out:
            self.skipTest("干净解释器 %s 缺依赖，无法核对真实环境：\n%s"
                          % (sys.executable, out[-400:]))
        self.assertEqual(proc.returncode, 0,
                         "真实环境与基线不一致（exit=%d）：\n%s" % (proc.returncode, out[-2000:]))
        self.assertIn("环境与基线一致", out)

    def test_gate_actually_fails_when_osmnx_uninstalled_in_subprocess(self):
        """手工那步"模拟 osmnx 消失→漂移→退出码 1"固化版。

        子进程里用 sitecustomize 式的 -c 预载一个空壳 osmnx，再跑 --loader，
        必须 exit 1 且报出 mode 漂移 —— 证明门禁在真实执行路径上会拦，不只是单测里自说自话。
        """
        prelude = ("import sys, types, runpy; "
                   "sys.modules['osmnx'] = types.ModuleType('osmnx'); "
                   "sys.argv = ['verify_data_provenance.py', '--loader']; "
                   "runpy.run_path(sys.argv[0], run_name='__main__')")
        proc = subprocess.run(
            [sys.executable, "-c", prelude, str(ROOT / "verify_data_provenance.py"), "--loader"],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        out = proc.stdout + proc.stderr
        self.assertNotIn("Traceback", out, "子进程崩溃不等于门禁真的生效：\n%s" % out[-1500:])
        if "No module named" in out and proc.returncode == 2:
            self.skipTest("干净解释器缺依赖，无法做 osmnx 消失实验：\n%s" % out[-400:])
        self.assertEqual(proc.returncode, 1,
                         "osmnx 被藏起来后门禁仍返回 %d，说明漂移检测是空的：\n%s"
                         % (proc.returncode, out[-2000:]))
        self.assertIn("mode=fallback", out, "FAIL 理由里必须点出是 mode 变了")


if __name__ == "__main__":
    unittest.main()
