# -*- coding: utf-8 -*-
"""S1 前置行为门：证明 patch 后的 swap_time 真的到达 runtime，而不是只改了配置文本。

为什么必须先有这道门（消费链实测）：
- `config/simulation.json` 里 swap_time_seconds 出现在 **7 处**：5 个 charging_stations、
  1 个 nest、1 个 drone；
- 运行时唯一生效的是 **station 值**——`frontend/environment.py:816` 调
  `drone.start_charging(st.station_id, swap_time_seconds=st.swap_time_seconds)`，
  `frontend/drone.py:206-208` 用它覆盖 `swap_remaining_steps`；
- station 由 `build_default_charging_stations()` 经 `get_shared_config()` 从磁盘构造。

因此本门不改主配置（那会污染工作树），而是走 runner 用的同一通道：
环境变量 ``SWARM_BALANCE_SIM_CONFIG`` 指向隔离配置文件，再断言构造出的对象携带该档值。
"配置被 patch 了"不等于"仿真吃到了"，所以判据一律从被测对象自己构造的状态上读回。
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
# frontend/*.py 内部用裸导入（environment.py:13 `from drone import ...`），
# 所以必须把 frontend/ 也放上 sys.path，否则 __import__ 直接 ModuleNotFoundError。
sys.path.insert(0, str(REPO / "frontend"))
CFG_PATH = REPO / "config" / "simulation.json"
SWAP_SITES = 7          # 5 station + 1 nest + 1 drone
OSM_PATH = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"


def _patched_cfg(swap: float) -> dict:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    for st in cfg["charging_stations"]:
        st["swap_time_seconds"] = swap
    cfg["nest"]["swap_time_seconds"] = swap
    cfg["drone"]["swap_time_seconds"] = swap
    return cfg


class _IsolatedConfig(unittest.TestCase):
    """基类：把 SWARM_BALANCE_SIM_CONFIG 指到临时配置，测完复原。"""

    def setUp(self):
        self._old_env = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
        self._tmpdir = tempfile.mkdtemp(prefix="swapgate_")

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
        else:
            os.environ["SWARM_BALANCE_SIM_CONFIG"] = self._old_env
        for f in pathlib.Path(self._tmpdir).glob("*"):
            f.unlink(missing_ok=True)
        os.rmdir(self._tmpdir)

    def _point_at(self, swap: float) -> str:
        p = pathlib.Path(self._tmpdir) / f"sim_{int(swap)}.json"
        p.write_text(json.dumps(_patched_cfg(swap), ensure_ascii=False), encoding="utf-8")
        os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(p)
        return str(p)


class ConfigSitesMoveTogether(_IsolatedConfig):
    def test_seven_sites_all_equal_patched_value(self):
        """判别式之一：7 处消费点若不同步改，patch 就是半生效。"""
        for swap in (60.0, 180.0, 300.0):
            path = self._point_at(swap)
            cfg = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
            vals = [float(s["swap_time_seconds"]) for s in cfg["charging_stations"]]
            vals.append(float(cfg["nest"]["swap_time_seconds"]))
            vals.append(float(cfg["drone"]["swap_time_seconds"]))
            self.assertEqual(len(vals), SWAP_SITES, f"消费点应为 {SWAP_SITES}，实得 {len(vals)}")
            self.assertTrue(all(v == swap for v in vals), f"{swap}: 存在未同步消费点 {vals}")


class StationsCarryPatchedValue(_IsolatedConfig):
    def test_station_objects_read_back_the_patched_value(self):
        """端到端：从真实 ChargingStation 对象读回，而不是从 dict 读回。"""
        from frontend.charging_station import build_default_charging_stations

        seen = {}
        for swap in (60.0, 180.0, 300.0):
            self._point_at(swap)
            stations = build_default_charging_stations()
            self.assertGreaterEqual(len(stations), 5, f"station 数异常: {len(stations)}")
            got = sorted({round(float(s.swap_time_seconds), 3) for s in stations})
            self.assertEqual(got, [swap], f"station 实际携带 {got}，期望 {[swap]}")
            seen[swap] = got
        self.assertEqual(seen[60.0], [60.0])
        self.assertEqual(seen[300.0], [300.0])

    def test_environment_wired_and_drone_defaults_follow(self):
        """environment 的 station 与无人机默认换电时长都必须是该档值。

        本断言只在**首个** Environment 构造上成立：`frontend/drone.py:25` 的
        DRONE_SWAP_TIME 是模块级常量，import 时就从盘求值；即便清掉 sys.modules
        重新 import，同一进程内第二次构造仍可能吃到已固化的旧值（实测第二轮拿到
        上一档的 60.0）。这正是 runner 采用"一配置一进程"的原因，故这里显式只测
        首构，并把多档扫描的隔离要求交给 S1 预设（每格独立子进程）。
        """
        swap = 180.0
        self._point_at(swap)
        em = __import__("frontend.environment", fromlist=["Environment"])
        e = em.Environment(str(OSM_PATH))
        st_vals = sorted({round(float(s.swap_time_seconds), 3) for s in e.charging_stations})
        self.assertEqual(st_vals, [swap], f"environment station={st_vals}，期望 {[swap]}")
        dr_vals = sorted({round(float(d.swap_time_seconds), 3) for d in e.drones})
        self.assertEqual(dr_vals, [swap], f"无人机默认换电时长={dr_vals}，期望 {[swap]}")

    def test_module_level_freeze_is_real_so_multi_config_needs_subprocess(self):
        """把"一配置一进程"这条前提变成会红的断言，而不是散文。

        必须在**独立子进程**里测：本类的其它用例已经在同进程构造过 Environment，
        模块级常量早已固化，断言会随 unittest 的执行顺序时红时绿（实测单跑 OK、
        进套件 FAIL）。所以这里自己起干净进程，两次 patch + 重导入做对照。

        判读：若第二次的无人机默认仍是第一档的值 ⇒ 模块级冻结存在 ⇒ 多档扫描必须
        一配置一进程。哪天 drone.py 改成实例级读取，子进程里第二次会跟随新配置，
        本断言转红，提醒"一配置一进程"的前提可以放宽——届时由人决定，不由我删测试。
        """
        probe = r'''
import json, os, sys, pathlib
repo = pathlib.Path(sys.argv[1]); tmp = pathlib.Path(sys.argv[2])
sys.path.insert(0, str(repo)); sys.path.insert(0, str(repo / "frontend"))
CFG = repo / "config" / "simulation.json"


def point_at(swap):
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    for st in cfg["charging_stations"]:
        st["swap_time_seconds"] = swap
    cfg["nest"]["swap_time_seconds"] = swap
    cfg["drone"]["swap_time_seconds"] = swap
    p = tmp / ("probe_%d.json" % int(swap))
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(p)


point_at(60.0)
import frontend.environment as em
first = em.Environment(str(repo / "frontend" / "data" / "map" / "part_of_yangpu.osm"))
v1 = round(float(first.drones[0].swap_time_seconds), 3)

point_at(300.0)
for name in list(sys.modules):
    if name.startswith(("frontend", "config")):
        del sys.modules[name]
import frontend.environment as em2
second = em2.Environment(str(repo / "frontend" / "data" / "map" / "part_of_yangpu.osm"))
st2 = sorted({round(float(s.swap_time_seconds), 3) for s in second.charging_stations})
dr2 = sorted({round(float(d.swap_time_seconds), 3) for d in second.drones})
print("PROBE v1=%s st2=%s dr2=%s" % (v1, st2, dr2))
'''
        import subprocess
        import tempfile as _tf

        d = _tf.mkdtemp(prefix="swapprobe_")
        script = pathlib.Path(d) / "probe.py"
        script.write_text(probe, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", str(script), str(REPO), d],
                               capture_output=True, text=True, timeout=600, encoding="utf-8",
                               errors="replace")
            line = next((ln for ln in (r.stdout or "").splitlines() if ln.startswith("PROBE ")), None)
            self.assertIsNotNone(line, f"探针没有产出读数 rc={r.returncode} stderr={(r.stderr or '')[-300:]}")
            fields = dict(kv.split("=", 1) for kv in line[len("PROBE "):].split())
            v1 = float(fields["v1"])
            st2 = fields["st2"]
            dr2 = fields["dr2"]
            self.assertEqual(v1, 60.0, f"子进程首构应为 60，实得 {v1}")
            self.assertEqual(st2, "[300.0]", f"station 每次从盘读，应为 [300.0]，实得 {st2}")
            self.assertNotEqual(dr2, "[300.0]",
                                f"干净进程里重导入后无人机默认已跟随新配置({dr2}) ⇒ 模块级冻结"
                                f"不存在，请同步放宽 S1 的『一配置一进程』前提并复核本节结论")
        finally:
            for f in pathlib.Path(d).glob("*"):
                f.unlink(missing_ok=True)
            os.rmdir(d)


class SwapActuallyBlocksDrone(_IsolatedConfig):
    """第二面：换电确实把无人机锁住那么久，否则扫 60 vs 300 没有区别。"""

    def test_swap_remaining_matches_station_value(self):
        for swap in (60.0, 300.0):
            self._point_at(swap)
            for name in list(sys.modules):
                if name.startswith(("frontend", "config")):
                    del sys.modules[name]
            em = __import__("frontend.environment", fromlist=["Environment"])
            e = em.Environment(str(OSM_PATH))
            d, st = e.drones[0], e.charging_stations[0]
            d.start_charging(st.station_id, swap_time_seconds=st.swap_time_seconds)
            self.assertTrue(d.is_charging, "start_charging 后应处于换电中")
            self.assertFalse(d.is_free, "换电期间不得可接单")
            self.assertEqual(round(float(d.swap_remaining_steps), 3), swap,
                             f"{swap} 档实得 {d.swap_remaining_steps}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
