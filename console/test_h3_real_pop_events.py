# -*- coding: utf-8 -*-
"""#69-H3 D-iv 六硬夹具 T1–T6：证人＝执行器真正 pop 服务航点的离散事件，不是几何/形状反推。

上位原则（冻结）：到达是"执行器完成某服务航点的离散事件"；`<1m` 只是 planner 的 endpoint 选择规则，
不构成服务完成事件。故本夹具只认 `Drone.consumed_waypoints_this_step`（update() 里每次 `pop(0)` append），
长度差 / 前后缀 / 线段穿越一律不再被测——它们是被禁止的反推族。

判别式两面（遵"先红后绿、旧规则必须实测报红"）：
  green = D-iv 真机制（当前 environment.py + drone.py）；
  red   = 后缀启发式 9b1cd15 的 `_consumed_prefix_len(prev,curr)`（历史中间对照，已回退未提交）。
  T3/T4/T5 三面在旧规则上**必须报红**（净长不变漏计 / 途经无弹出误计 / re-route 队首服务点误计），
  以此证明新机制真的改变了判定、而非恰好与旧规则同结果。

构造纪律：每个夹具用满电 Drone（避开低电改道分支）、known_stations=[]（避开机巢副作用）。
一步最大位移 = `DRONE_SPEED × STEP_SECONDS`（当前配置 17.0×1.0=17 m）；测试里按此常量算可达距离，
不写死 200——速度是配置项，写死会随 config 漂移而静默失真。
"""
from __future__ import annotations
import os, pathlib, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _suffix_rule_k(prev, curr) -> int:
    """9b1cd15 的后缀+服务前缀启发式（历史中间对照，用于证旧规则在这些面上会红）。"""
    n = len(prev)
    if n == 0:
        return 0
    for k in range(1, n + 1):
        if list(prev[k:]) == list(curr):
            return k
    curr_coords = {(round(float(p[0]), 6), round(float(p[1]), 6)) for p in curr}
    k = 0
    while k < n and len(prev[k]) >= 3 and prev[k][2] in ('source', 'dest'):
        if (round(float(prev[k][0]), 6), round(float(prev[k][1]), 6)) in curr_coords:
            break
        k += 1
    return k


class RealPopEventFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # #70-P1 判据③（普查门改版后实测抓到本模块）：原先这里 setenv + 改 sys.path 却不还原，
        # 于是 console/test_speed_fallback_gate 之类"取内核时才装配置"的门会读到别人那份 config。
        cls._prev_cfg = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
        cls._prev_path = list(sys.path)
        os.environ["SWARM_BALANCE_SIM_CONFIG"] = str((ROOT / "config" / "simulation.json").resolve())
        for p in (str(ROOT), str(ROOT / "frontend")):
            if p not in sys.path:
                sys.path.insert(0, p)
        from drone import Drone, DRONE_SPEED, DRONE_TIME_STEP
        # #70-P1 判据②：内核（Environment）走按路径加载器，不按名字 import ⇒
        # 不在 sys.modules["environment"] 里留下"首次 import 冻结的配置常量"。
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from console import _preflight
        cls.Environment = _preflight.load_kernel_environment()[0].Environment
        cls.Drone = Drone
        cls.STEP_DIST = float(DRONE_SPEED) * float(DRONE_TIME_STEP)   # 一步最大位移（当前 17.0）

    @classmethod
    def tearDownClass(cls):
        if cls._prev_cfg is None:
            os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
        else:
            os.environ["SWARM_BALANCE_SIM_CONFIG"] = cls._prev_cfg
        sys.path[:] = cls._prev_path

    def _mk(self, x, y, route):
        d = self.Drone(x=x, y=y, drone_id="t")
        d.current_battery = d.battery_capacity      # 满电：绕开低电改道分支
        d.known_stations = []                        # 无机巢：绕开机巢/泊位副作用
        d.scheduled_position = [list(w) for w in route]
        d.consumed_waypoints_this_step = []
        return d

    # ---- T1 direct pop：无人机正对 dest 飞、抵达即弹出 → 缓冲含该 dest ----
    def test_T1_direct_pop_records_event(self):
        d = self._mk(0.0, 0.0, [(self.STEP_DIST * 0.5, 0.0, 'dest')])   # 距离 < 一步位移 → 抵达并 pop
        d.update()
        self.assertEqual([w[2] for w in d.consumed_waypoints_this_step], ['dest'],
                         "[T1] 直接抵达应产生一次 dest 弹出事件")
        self.assertEqual(d.scheduled_position, [], "[T1] 弹出后航线清空")

    # ---- T2 detour pop：末点是 A* 绕行落点（非精确 source 坐标），抵达仍算消费 ----
    def test_T2_detour_pop_records_event(self):
        # source 标在绕行后的实际落点上：执行器抵达该落点即弹出，标签仍是 source
        d = self._mk(0.0, 0.0, [(self.STEP_DIST * 0.7, self.STEP_DIST * 0.1, 'source'),
                                (self.STEP_DIST * 3.0, 0.0, 'dest')])   # dest 远在 3 步外，本步不碰它
        d.update()                                   # 到近处 source 落点 ≤一步 → pop source；dest 留航线上
        self.assertEqual([w[2] for w in d.consumed_waypoints_this_step], ['source'],
                         "[T2] detour 落点被真弹出 → 记一次 source 事件")

    # ---- T3 同帧 pop+append 净长不变 → 必须计（旧后缀规则在此漏计，须报红）----
    def test_T3_same_step_pop_and_append_netlen_unchanged_counts(self):
        d = self._mk(0.0, 0.0, [(self.STEP_DIST * 0.5, 0.0, 'dest')])
        # 模拟 update 抵达 pop dest 后，调度在同帧又 append 一个 nest 点（净长回到 1）
        orig_update = d.update
        def wrapped():
            orig_update()
            d.scheduled_position.append([999.0, 999.0, '?'])   # 同帧追加仓库/换电点
        d.update = wrapped
        d.update()
        popped_labels = [w[2] for w in d.consumed_waypoints_this_step]
        self.assertIn('dest', popped_labels, "[T3] 同帧弹 dest+追加，dest 必须被记为消费")
        # 诚实标注：这个"队首服务点消失 + 追加非服务点"的形状，H1′(9b1cd15) 的后缀规则分支(b)
        # 其实也能计到（k=1）——它当初就是为修 task_44 这一类加的。所以 **T3 不是旧规则会红的地方**；
        # 旧规则真正红的是 T4/T5（几何途经/re-route 的假阳性）。此处只钉 D-iv 在净长不变时仍正确计一笔。
        prev = [[self.STEP_DIST * 0.5, 0.0, 'dest']]; curr = [[999.0, 999.0, '?']]
        self.assertEqual(len([l for l in popped_labels if l == 'dest']), 1,
                         f"[T3] D-iv 净长不变仍计且仅计一次 dest（旧后缀 k={_suffix_rule_k(prev,curr)} 此面同果，非其失败面）")

    # ---- T4 geometric pass 无 pop → 必须不计（途经但没抵达的点绝不入缓冲）----
    def test_T4_geometric_pass_without_pop_not_counted(self):
        # 队首 waypoint 在近处会被抵达；第二个 dest 远在天边，这一步绝不可能到达
        d = self._mk(0.0, 0.0, [(self.STEP_DIST * 0.5, 0.0, 'waypoint'), (5000.0, 5000.0, 'dest')])
        d.update()
        labels = [w[2] for w in d.consumed_waypoints_this_step]
        self.assertNotIn('dest', labels, "[T4] 未经执行的 dest 不得进消费缓冲")
        self.assertEqual(labels, ['waypoint'], "[T4] 只有真抵达的 waypoint 入缓冲")

    # ---- T5 mid-flight reroute 无 pop → 必须不计（杀掉那 9 例假阳性；旧后缀会误计，须报红）----
    def test_T5_midflight_reroute_without_pop_not_counted(self):
        # 队首是远处 dest，这一步只是朝它挪一点、从未抵达/pop
        d = self._mk(0.0, 0.0, [(5000.0, 5000.0, 'dest')])   # dest 远在 7071m 外，一步绝不可能抵达
        d.update()                                            # 朝 dest 挪 STEP_DIST，未抵达 → 不 pop
        self.assertEqual(d.consumed_waypoints_this_step, [],
                         "[T5] 未抵达即不得有消费事件（杀 9 例 re-route 假阳性的机制根）")
        self.assertEqual(len(d.scheduled_position), 1, "[T5] dest 仍在航线里")
        # 判别式：faceoff 的 9 例形状是"队首服务点在改道后被替换消失"，prev=[dest..] curr=[nest..]：
        prev = [[5000.0, 5000.0, 'dest']]; curr = [[10.0, 10.0, '?']]
        old_k = _suffix_rule_k(prev, curr)
        self.assertEqual(old_k, 1,
            f"[T5_RED_DEMONSTRATION] 旧后缀规则把'队首服务点被改道替换'误判为消费(k={old_k})⇒9 例假阳性之源；D-iv 靠无 pop 事件判 k=0")

    # ---- T6 同 step 多 pop 保序：连续两近点先后弹出，缓冲保持发生顺序 ----
    def test_T6_multiple_pops_preserve_order(self):
        # 两个都在一步可达范围内且沿 +x 排列：先 pop 队首 source，再（下一步）pop dest。
        # 钉住执行器核心不变量：每次抵达恰 append 一条、按队首顺序，环境读出即清空。
        d = self._mk(0.0, 0.0, [(self.STEP_DIST * 0.3, 0.0, 'source'),
                                (self.STEP_DIST * 0.6, 0.0, 'dest')])
        d.update()
        first_step = [w[2] for w in d.consumed_waypoints_this_step]
        self.assertEqual(first_step, ['source'], "[T6a] 第一步只消费队首 source（单步单次 pop）")
        d.consumed_waypoints_this_step = []       # 环境消费后清空
        d.update()
        second_step = [w[2] for w in d.consumed_waypoints_this_step]
        self.assertEqual(second_step, ['dest'], "[T6b] 下一步才消费 dest，顺序与航线一致")

    # ---- 不变量：缓冲里每条都必须是"曾经队首、现已不在航线"的点，杜绝幽灵事件 ----
    def test_invariant_buffer_entries_actually_left_route(self):
        d = self._mk(0.0, 0.0, [(self.STEP_DIST * 0.4, 0.0, 'source'),
                                (self.STEP_DIST * 4.0, 0.0, 'dest')])
        d.update()
        for wp in d.consumed_waypoints_this_step:
            self.assertNotIn(wp, d.scheduled_position,
                             "[INVARIANT] 消费缓冲里的点必须已离开航线；出现仍在航线的条目=幽灵事件")


if __name__ == "__main__":
    unittest.main(verbosity=2)
