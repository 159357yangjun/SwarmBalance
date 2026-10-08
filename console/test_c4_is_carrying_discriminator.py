# -*- coding: utf-8 -*-
"""#69-C4 加固①：`_is_carrying` 判别式夹具 —— 钉住"载货真值来自航线形状，不是 current_load"。

背景（#69-C3 审计结论）：`current_load` 一名两义——add_load 在**派单时刻**就调用
（environment.py:1109/1121/1818），所以它表示"已指派重量"而非"机上物理有货"。
`_is_carrying`(environment.py:1741) 是 KPI `empty_load_ratio` 的唯一消费点（env:1168），
必须按航线上下一个任务航点定夺，不能退化成 `current_load > 0`。

两面都要（缺一即是一扇只会绿的门）：
  F1 已 add_load 但下一航点是 source ⇒ 必须 False（飞往取货段＝空驶）
  F2 dest 仍在航线上且 load 未扣    ⇒ 必须 True （送货段＝带货）
  F3 只剩 waypoint、无服务航点      ⇒ 必须 False（空驶调度；防"route 里有 dest 才判"这种错写法蒙对前两面）

变异面（MUT）：把 `_is_carrying` 换成被禁止的 `current_load > 0` ⇒ **F1 必须先咬**（load>0 却该 False）。
短码：[C4_F1_EMPTY_LEG]/[C4_F2_LOADED_LEG]/[C4_F3_DEADHEAD]/[C4_MUT_NOT_CAUGHT]
"""
from __future__ import annotations
import os, pathlib, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# #70-P1 判据②：内核改走 console/_preflight.py 的按路径加载器（只在 setUpClass 里取），
# 不在 import 期 `from environment import ...` —— 首次 import 会冻结
# frontend/environment.py:87/:100/:105 的配置常量，令后续依赖别的配置的模块静默拿到出厂值。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from console import _preflight  # noqa: E402

# ⚠ 不能把 staticmethod 存成类属性再 `_is_carrying(d)` 调：那样 Python 会把 self 注进去
#   （本轮实测报 takes-1-positional-but-2）。走模块级函数名调用，绑定与生产代码一致。
_IC = None


def _is_carrying(drone):
    return _IC(drone)


class IsCarryingDiscriminator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _IC
        # #70-P1 判据③：进门记账、退出还原（由 console/test_p3_no_cross_test_residue.py 守）。
        cls._prev_cfg = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
        cls._prev_path = list(sys.path)
        os.environ["SWARM_BALANCE_SIM_CONFIG"] = str((ROOT / "config" / "simulation.json").resolve())
        for p in (str(ROOT), str(ROOT / "frontend")):
            if p not in sys.path:
                sys.path.insert(0, p)
        kernel = _preflight.load_kernel_environment()[0]
        Environment = kernel.Environment
        from drone import Drone
        raw = Environment.__dict__.get('_is_carrying')
        _IC = raw.__func__ if isinstance(raw, staticmethod) else raw
        cls.Drone = Drone

    @classmethod
    def tearDownClass(cls):
        if cls._prev_cfg is None:
            os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
        else:
            os.environ["SWARM_BALANCE_SIM_CONFIG"] = cls._prev_cfg
        sys.path[:] = cls._prev_path

    def _d(self, load, route):
        d = self.Drone(x=0.0, y=0.0, drone_id="c4")
        d.current_battery = d.battery_capacity
        d.known_stations = []
        d.current_load = float(load)
        d.scheduled_position = [list(w) for w in route]
        return d

    # ---- F1：派单后飞往取货点——字段说有货，航线说没有 ⇒ 必须 False ----
    def test_F1_dispatched_but_enroute_to_source_is_not_carrying(self):
        d = self._d(5.0, [(100.0, 0.0, 'source'), (200.0, 0.0, 'dest')])
        self.assertFalse(_is_carrying(d),
                         "[C4_F1_EMPTY_LEG] 已 add_load 但下一航点是 source ⇒ 还没取货，应判空驶")

    # ---- F2：已在送货途中 ⇒ 必须 True ----
    def test_F2_dest_leg_is_carrying(self):
        d = self._d(5.0, [(200.0, 0.0, 'dest')])
        self.assertTrue(_is_carrying(d),
                        "[C4_F2_LOADED_LEG] dest 仍在航线上且未卸货 ⇒ 应判带货")

    # ---- F3：只剩普通 waypoint（空驶调度/返巢）⇒ 必须 False ----
    def test_F3_deadhead_route_is_not_carrying(self):
        d = self._d(5.0, [(200.0, 0.0, 'waypoint')])
        self.assertFalse(_is_carrying(d),
                         "[C4_F3_DEADHEAD] 航线里没有任何服务航点 ⇒ 空驶，不得因 load>0 判带货")

    # ---- 承重变量判别式：同一航线形状下只动 current_load，答案不该变（证明证人不是 load）----
    def test_shape_is_the_witness_not_load(self):
        route = [(100.0, 0.0, 'source'), (200.0, 0.0, 'dest')]
        with_load = _is_carrying(self._d(5.0, route))
        no_load = _is_carrying(self._d(0.0, route))
        self.assertEqual(with_load, no_load,
                         "[C4_LOAD_LEAKED_IN] 同航线形状仅改 current_load 就翻转 ⇒ 判定吃进了派单重量")

    # ---- 变异面：证明这扇门真的会拦下退化写法 ----
    def test_mutation_current_load_rule_is_caught(self):
        """把 _is_carrying 换成被禁止的 `current_load > 0`，本夹具必须报红并具名是哪一面先咬。"""
        bad = lambda d: float(getattr(d, 'current_load', 0.0)) > 0
        faces = {
            "F1": (self._d(5.0, [(100.0, 0.0, 'source'), (200.0, 0.0, 'dest')]), False),
            "F2": (self._d(5.0, [(200.0, 0.0, 'dest')]), True),
            "F3": (self._d(5.0, [(200.0, 0.0, 'waypoint')]), False),
        }
        caught = [name for name, (d, want) in faces.items() if bad(d) != want]
        self.assertTrue(caught,
                        "[C4_MUT_NOT_CAUGHT] 退化成 current_load>0 竟没让任何一面翻转 ⇒ 夹具无牙")
        self.assertIn("F1", caught,
                      f"[C4_MUT_FACE_ORDER] 预期 F1 先咬（load>0 却该 False），实际咬={caught}")
        print("[C4_MUTATION] 退化写法 current_load>0 被这些面抓到：%s（F1 先咬）" % ",".join(sorted(caught)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
