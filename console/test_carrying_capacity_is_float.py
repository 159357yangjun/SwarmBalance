# -*- coding: utf-8 -*-
"""机型载重必须是浮点：`int()` 会把 light_express 的 2.4 kg 静默截成 2 kg。

来历（不是设想，是本轮实测撞出来的）：`4d956e6` 之前 `frontend/drone.py:26/48` 两处用
`int(_DRONE_CFG.get("carrying_capacity", …))` 读配置，运行时实测拿到 2 —— 而配置文件、README
与两份文档印的都是 2.4。这不只是显示问题：**同 seed 的结项实验里"总步数 2274→2049、
超时率 0.0833→0.0667、平均时延 4.7250→2.5833"**（父提交 `638cffe` vs `4d956e6` 各跑四算法对照）。
也就是说归档那批 68 次运行是在一个与配置不一致的参数下测出来的。

为什么要一条常驻用例：那个修复当时**没有任何断言钉住**（全仓搜 `carrying_capacity` 只有别的
测试自造的 capacity 值），所以谁把 `float` 改回 `int` 都不会红 —— 而这一处一旦退回，
指标会整批漂移且没人知道。判别式写在下面两条里：源码形状 + 行为后果，摘掉 float 必红。
"""
from __future__ import annotations

import io
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
import sys                                        # noqa: E402
for _p in (str(ROOT), str(FRONTEND)):              # drone.py 自己平铺 import 兄弟模块
    if _p not in sys.path:
        sys.path.insert(0, _p)
if str(ROOT / "console") not in sys.path:
    sys.path.insert(0, str(ROOT / "console"))
import _preflight                                 # noqa: E402

_preflight.require("numpy", "shapely", gated_in="console/test_carrying_capacity_is_float.py")

CFG_PATH = ROOT / "config" / "simulation.json"
DRONE_SRC = ROOT / "frontend" / "drone.py"
# 与 frontend/drone.py 里那两处读取同形的"被截断"形状：int(...carrying_capacity...)
INT_TRUNC = re.compile(r"\bint\(\s*[^)]*carrying_capacity")


def _truncations(src):
    return [i + 1 for i, line in enumerate(src.splitlines()) if INT_TRUNC.search(line)]


def _types():
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    return cfg["heterogeneous"]["drone_types"], cfg["drone"].get("carrying_capacity")


class CarryingCapacityIsFloatTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.types, cls.default = _types()

    def test_config_actually_has_a_fractional_payload(self):
        """前提不成立就别往下测：若配置里全是整数，这条门就成了摆设。"""
        frac = {k: v["carrying_capacity"] for k, v in self.types.items()
                if float(v["carrying_capacity"]) != int(float(v["carrying_capacity"]))}
        self.assertTrue(frac,
                        "配置里已没有任何小数载重，本用例的判据空转 —— 要么改配置说明、"
                        "要么删掉这条用例，别留一条永远不会红的门")
        print("[CAP_CONFIG] 小数载重机型=%s" % json.dumps(frac, ensure_ascii=False))

    def test_runtime_payload_equals_config_value(self):
        """正例：Drone 按机型建出来之后，载重必须**逐位等于**配置值（含 2.4）。

        加载走 `_preflight.load_frontend_module`（按文件路径），不写 `from frontend.drone import`
        —— 那条路会撞上 `frontend/drone.py` 自己的平铺 import（`charging_station`），
        而且名字撞车是这仓真踩过的事（见 console/test_command_console.py 的桩泄漏）。
        """
        drone_mod = _preflight.load_frontend_module("drone")
        Drone = drone_mod.Drone
        for name, spec in sorted(self.types.items()):
            d = Drone(0.0, 0.0, drone_id=name, drone_type=name)
            self.assertEqual(d.carrying_capacity, float(spec["carrying_capacity"]),
                             "%s 运行时载重=%r，配置=%r —— 被截断了？"
                             % (name, d.carrying_capacity, spec["carrying_capacity"]))
            self.assertIsInstance(d.carrying_capacity, float,
                                  "%s 的载重类型是 %s，不是 float" % (name, type(d).__name__))
        light = Drone(0.0, 0.0, drone_id="L", drone_type="light_express")
        self.assertGreater(light.carrying_capacity, 2.0,
                           "light_express 又变回 2 kg 了（实测值 %r）" % light.carrying_capacity)
        # 默认值那条路也印一次实际拿到的数（异构关闭时走 :26 那个 DEFAULT_*）
        print("[CAP_RUNTIME] light_express=%r default=%r hetero=%s"
              % (light.carrying_capacity, drone_mod.DEFAULT_CARRYING_CAPACITY,
                 drone_mod.HETERO_ENABLED))

    def test_default_path_is_float_too(self):
        """默认值那条路（非异构机型）也要核：`:26` 原先同样写的是 int()。"""
        src = DRONE_SRC.read_text(encoding="utf-8")
        m = re.search(r"^DEFAULT_CARRYING_CAPACITY\s*=\s*(\w+)\(", src, re.M)
        self.assertIsNotNone(m, "读不到 DEFAULT_CARRYING_CAPACITY 的构造方式，判据空转")
        self.assertEqual(m.group(1), "float",
                         "默认载重又变成 %s() 了 —— 会把 %r 截断" % (m.group(1), self.default))

    def test_no_int_truncation_left_in_the_type_branch(self):
        """源码级门：机型分支里不许再出现 `int(...carrying_capacity...)`。

        为什么不只靠行为断言：如果哪天有人加一条 `carrying_capacity=int(...)` 在别处覆盖，
        行为用例可能仍被别的默认值掩盖；这条扫描是**同一处缺陷的第二面**。
        """
        src = DRONE_SRC.read_text(encoding="utf-8")
        bad = _truncations(src)
        self.assertEqual(bad, [],
                         "frontend/drone.py 这些行又用 int() 读 carrying_capacity：%s" % bad)

    def test_detector_is_not_vacuous(self):
        """判别式：把 `float(` 换成 `int(` 之后，上面那条源码门必须点名这一行。"""
        src = DRONE_SRC.read_text(encoding="utf-8")
        perturbed = src.replace('carrying_capacity = float(type_cfg.get',
                                'carrying_capacity = int(type_cfg.get', 1)
        self.assertNotEqual(perturbed, src, "扰动没改动任何字节，下面的核对是空转")
        bad = _truncations(perturbed)
        self.assertEqual(len(bad), 1, "扰动后应恰好抓到 1 行，实得 %s" % bad)
        # 还原自检：真文件里这条模式必须为 0，否则上面那条门此刻就是红的
        self.assertEqual(_truncations(src), [], "当前源码里就有 int(carrying_capacity) —— 先修它")


if __name__ == "__main__":
    unittest.main()
