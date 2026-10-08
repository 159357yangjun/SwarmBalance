# -*- coding: utf-8 -*-
"""#69-C1 destination-leg 语义夹具：direct / detour / fallback-single / mutation 四组。

与 #69-B 的 source-leg 夹具（test_r2_destination_without_load.py）对称，**全部走真实 planner 出口**
`Environment.plan_route_for_tasks`（真实装配 + 真实 A*），只检查它产出的航点标签表；不复刻标签逻辑。

契约（本轮唯一改动，planner 零修改）：destination leg 的前 N-1 个 waypoint = transit，
最后 1 个 waypoint = **dest service waypoint**（标签 'dest'）。送达由"该服务航点被消费"触发
（environment.py:1205 消费块），不再额外要求 position == task.destination 精确相等——
那与标签构成两套到达判据，会在 A* <1 m 容差抵达下永远失配 ⇒ 无 DESTINATION_REACHED 却被
is_free 兜底计成完成（即 #69-A/#69-C0 定位的缺陷形态）。

四组各自钉住的东西：
  A direct           无障碍直达          ⇒ dest leg 末点带 'dest'，且全表恰一个 dest 标签
  B detour           必穿楼需绕障        ⇒ transit 若干 + 服务航点 'dest'；**不要求坐标等于 destination**
                                        （实测本机 18/18 绕障对的服务航点均非精确终点 ⇒ 这条真有覆盖）
  C fallback-single  规划退化到单点      ⇒ 仍产出恰一个 'dest' 服务航点（不因分支不同而漏标）
  D mutation         静态守卫            ⇒ 消费侧不得再出现「标签 + 坐标严格相等」两套判据并存

纪律：不改 planner、不改 drone.py、不改 cleanup accounting、不改 TaskState/scheduler/KPI 定义。
"""
from __future__ import annotations

import math
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# #70-P1 判据②：不在 import 期按名字加载 environment（frontend/environment.py:87/:100/:105
# 会在首次 import 时把配置常量冻结掉，谁先 import 决定全进程看到什么 ⇒ 顺序敏感）。
# 改走 console/_preflight.py 的按路径加载器：不进 sys.modules["environment"]、不污染别人。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from console import _preflight  # noqa: E402


class DestLegSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # #70-P1 判据③：进门记账、退出还原 —— 本模块会改环境变量与 sys.path。
        cls._prev_cfg = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
        cls._prev_path = list(sys.path)
        os.environ["SWARM_BALANCE_SIM_CONFIG"] = str((ROOT / "config" / "simulation.json").resolve())
        for p in (str(ROOT), str(ROOT / "frontend")):
            if p not in sys.path:
                sys.path.insert(0, p)
        Environment = _preflight.load_kernel_environment()[0].Environment
        cls.Environment = Environment
        cls.OSM = str(ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm")
        env = Environment(cls.OSM, episode_max_steps=2)
        env.reset(seed=40913)
        cls.env = env
        bb = env.global_bounds
        cls.cx = (bb[0] + bb[2]) / 2.0
        cls.cy = (bb[1] + bb[3]) / 2.0

    @classmethod
    def tearDownClass(cls):
        # 还原到"本模块 setUpClass 之前"的状态（判据③；由 console/test_p3_no_cross_test_residue.py 守）。
        if cls._prev_cfg is None:
            os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
        else:
            os.environ["SWARM_BALANCE_SIM_CONFIG"] = cls._prev_cfg
        sys.path[:] = cls._prev_path

    def _route_tags(self, start, src, dst):
        class _T:
            def __init__(s, a, b):
                s._a, s._b = tuple(a[:2]), tuple(b[:2])
            def get_source(s): return s._a
            def get_destination(s): return s._b
        d = self.env.drones[0]
        d.x, d.y = float(start[0]), float(start[1])
        route = self.env.plan_route_for_tasks(d, [_T(src, dst)])
        return [(p[0], p[1], p[2]) for p in route], (tuple(src[:2]), tuple(dst[:2]))

    def _dest_leg(self, tags):
        """切出 dest leg：从第一个 'source' 标签之后到表尾（source 服务点本身不算 dest leg）。"""
        si = next((i for i, t in enumerate(tags) if t[2] == 'source'), -1)
        return tags[si + 1:] if si >= 0 else tags

    # ---------------- A. direct -------------------------------------
    def test_A_direct_has_exactly_one_dest_tag(self):
        if not self.env.is_path_clear((self.cx, self.cy), (self.cx + 5.0, self.cy)):
            self.skipTest("[A_NEEDS_CLEAR_CORRIDOR] 世界未给出直达走廊")
        start = (self.cx, self.cy)
        src = (self.cx + 5.0, self.cy)
        dst = (self.cx + 400.0, self.cy)
        tags, (s, e) = self._route_tags(start, src, dst)
        kinds = [t[2] for t in tags]
        self.assertEqual(kinds.count('dest'), 1,
                         f"[A_DEST_TAG_COUNT] {kinds} ⇒ 全表应恰有一个 dest 服务航点")
        self.assertEqual(kinds[-1], 'dest', "[A_DEST_NOT_LAST] dest 服务航点必须是全表末点")

    # ---------------- B. detour -------------------------------------
    def test_B_detour_service_waypoint_is_last_of_leg(self):
        """必穿楼 ⇒ dest leg 有 transit；服务航点是末点，且**不要求其坐标等于 destination**。"""
        hs = getattr(self.env, "high_buildings", []) or []
        if not hs:
            self.skipTest("[B_NO_OBSTACLE_IN_WORLD] 本机环境无 >20 m 建筑")
        picked = None
        for hb in hs:
            b = hb["geometry"].bounds
            bcx, bcy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
            span = max(b[2] - b[0], b[3] - b[1], 1.0)
            src, dst = (bcx - span * 3, bcy), (bcx + span * 3, bcy)
            if not self.env.is_path_clear(src, dst):
                picked = (src, dst)
                break
        if picked is None:
            self.skipTest("[B_NO_BLOCKED_PAIR] 没有穿楼起终点对可触发绕障")
        src, dst = picked
        tags, (s, e) = self._route_tags(src, src, dst)
        leg = self._dest_leg(tags)
        kinds = [t[2] for t in leg]
        self.assertGreater(len(leg), 1, "[B_NO_TRANSIT] 绕障却没产生 transit 航点")
        self.assertEqual(kinds.count('dest'), 1, f"[B_DEST_TAG_COUNT] {kinds}")
        self.assertEqual(kinds[-1], 'dest', "[B_SERVICE_NOT_LAST]")
        near = math.hypot(leg[-1][0] - e[0], leg[-1][1] - e[1])
        self.assertLess(near, 1.5,
                        f"[B_SERVICE_TOO_FAR] dest 服务航点距终点 {near:.3f} m，超出既有容差语义")
        self.assertEqual(kinds[:-1].count('dest'), 0, "[B_TRANSIT_MISLABELED]")
        # 关键覆盖证明：这条 leg 的服务航点是否**恰好**等于 destination？
        exact = abs(leg[-1][0] - e[0]) < 1e-9 and abs(leg[-1][1] - e[1]) < 1e-9
        print(f"[B_INFO] dest 服务航点是否精确等于 destination: {exact}"
              f"（False 才真正覆盖到容差抵达这条路径）")

    # ---------------- C. fallback-single -----------------------------
    def test_C_fallback_still_labels_service_point(self):
        """规划退化（终点在障碍内 / 无可达绕行）时仍必须产出恰一个 'dest' 服务航点。

        取一个落在高楼内部的终点：plan_route_around_buildings 会走 fallback 返回 (end,)，
        装配循环对它应用同一规则（n_leg=1 ⇒ 唯一点 = dest），不得因分支不同而漏标。
        """
        hs = getattr(self.env, "high_buildings", []) or []
        if not hs:
            self.skipTest("[C_NO_OBSTACLE_IN_WORLD]")
        b = hs[0]["geometry"].bounds
        bcx, bcy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        src = (bcx - 300.0, bcy)
        dst = (bcx, bcy)                       # 终点落在楼体中心
        tags, (s, e) = self._route_tags(src, src, dst)
        kinds = [t[2] for t in tags]
        self.assertEqual(kinds.count('dest'), 1,
                         f"[C_DEST_TAG_COUNT] {kinds} ⇒ fallback 分支丢了 dest 服务航点")
        self.assertEqual(kinds[-1], 'dest', "[C_DEST_NOT_LAST]")

    # ---------------- D. mutation / 静态守卫 --------------------------
    def test_D_consumer_requires_label_only(self):
        """静态守卫：dest 消费侧不得再出现「标签 + 坐标严格相等」两套判据并存。

        若有人把 `get_destination() == dest_pos` 加回消费块，本用例当场红——这正是 #69-C1
        移除的那条第二判据；它在 direct/fallback 下不会出错，只在 detour 容差抵达下静默失效，
        所以必须由这条文本哨兵守着，而不是靠某个能通过的运行样本。
        """
        src = pathlib.Path(ROOT / "frontend" / "environment.py").read_text(encoding="utf-8")
        i = src.find("popped[2] == 'dest'")
        self.assertGreater(i, 0, "[D_CONSUMER_GONE] 找不到送达消费块，检查是否被改名")
        block = src[i:i + 900]
        self.assertNotIn("get_destination() == dest_pos", block,
                         "[D_DOUBLE_CRITERION_REINTRODUCED] 坐标严格相等判据被加回来了")
        # dest_pos 这个变量本身也不应再残留（旧代码用它做相等比较）
        self.assertNotIn("dest_pos = (popped[0], popped[1])", block,
                         "[D_DEAD_VAR_RESURRECTED] dest_pos 已无用，留着说明相等判据可能回来")


if __name__ == "__main__":
    unittest.main(verbosity=2)
