# -*- coding: utf-8 -*-
"""建筑高度进入规划的方式 = `height > 20 m` 的**二值障碍规则**（不是三维规避，也不是渲染装饰）。

为什么值得一条门（2026-10-06）：我在对话里把这件事说成了"UI 楼高是渲染装饰、不参与路径可行性"，
那是把两个不同命题混成一句 ——
  · 「z / altitude 不进三维航迹」＝对；
  · 「height 不进决策」＝**错**：它决定这栋楼参不参与障碍集合。
文档 `docs/模型真实结构修订.md §2.2` 自始写的是正确机制，但**只有散文没有门**，
所以措辞可以随口复发。本文件把该口径钉成断言。

三条判据（缺一不可，各自对应一种会说错的表述）：
  H1 **阈值承重**：同一栋楼几何不变、只把 height 从 25 改成 15 ⇒ 必须从障碍集合消失。
     （若这条不红，说明障碍集合其实按面积/名称筛，"二值高度阈值"这句话就是假的。）
  H2 **高度值本身不被消费**：25 m 与 250 m 必须给出**逐位相同**的可通行性判定。
     （若这条红，说明模型已偷偷引入三维 ⇒ §2.2 与总纲 §3.2 都要重写。）
  H3 **过阈值即无限高棱柱**：穿过 25 m 楼的直线路径必须判为不可通行，
     且把该楼 height 抬到 1e9 后仍不可通行（等价于"多高都一样"）。
两面取差分：H1 用低阈值面证"阈值会改变结果"，H2/H3 用同几何不同高度证"高度大小不改变结果"。

⚠ 本文件顶部必须关掉 `is_path_clear` 的**磁盘**缓存（`SWARM_BALANCE_PATHCLEAR_CACHE=0`）：
障碍结果桶按「楼数 + 各楼 wkt」取指纹（`environment.py:2037-2043`），而 H1/H2 刻意让**几何保持
不变、只改 height** ⇒ 所有面命中同一个桶。第一轮实测就是这样把 H1 的低阈值面读成上一轮的
`False`（假红）。清掉实例缓存不够，桶本身是进程级 + 落盘的，所以走官方开关而不是绕它。
"""
from __future__ import annotations

import os

# ⚠ 开关只在**本门运行期间**生效，绝不能在模块顶层写死：discover 是同进程按字母序跑的，
# 顶层 setenv 会一路污染后面的模块 —— 本轮实测就是这样让 `test_server_guards` 的
# PathClearBucketFingerprintTests 变红（它断言"几何还原后回到同一个桶"，而那个桶的内容
# 取决于磁盘缓存开不开）。setUp/tearDown 成对切换才是正确形状。
_TOGGLE = "SWARM_BALANCE_PATHCLEAR_CACHE"

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "frontend"))

OSM = ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm"
THRESHOLD_NOTE = "environment.py 的 HIGH_BUILDING_MIN_HEIGHT_M(=20)"


def shapely_affine(poly, dx):
    """把楼沿 x 平移 dx 米 —— 只为让障碍几何指纹不同，穿/不穿的结论不受影响。"""
    from shapely.affinity import translate
    return translate(poly, xoff=dx)


class _EmptyNoFly:
    """把禁飞区从判定链里摘干净，使 H1 的两面差分只由高度阈值这一个变量产生。"""

    def path_blocked(self, pos1, pos2):
        return False


def _kernel():
    """#70-P1 判据②：内核走 console/_preflight.py 的按路径加载器。

    本门要读写**进程级** `environment._PATH_CLEAR_BUCKETS`（见 tearDownClass 的还原理由），
    所以必须拿到"自己这次加载的那个模块对象"，而不是靠名字去 sys.modules 里抢 ——
    按名字 import 会把首次 import 的配置冻结留给全进程（顺序敏感的根因就在这）。
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from console import _preflight
    return _preflight.load_kernel_environment()[0]


def _env(kernel):
    env = kernel.Environment(str(OSM), episode_max_steps=1)
    env.reset(seed=40901)
    return env


class HeightBinaryGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not OSM.is_file():
            raise unittest.SkipTest("缺内置地图 part_of_yangpu.osm")
        # 成对切换（见文件顶 _TOGGLE 的注释）：本门靠"每个面用不同几何"来避开桶复用，
        # 关磁盘缓存只是防止把合成楼的判定写进仓内缓存、被后续真实实验读回。
        cls._prev_toggle = os.environ.get(_TOGGLE)
        os.environ[_TOGGLE] = "0"
        cls._kernel = _kernel()
        cls._orig_buckets = dict(cls._kernel._PATH_CLEAR_BUCKETS)   # 见 tearDownClass 的还原理由
        cls.env = _env(cls._kernel)
        # 造一栋合成楼：几何固定，只换 height —— 不用真楼，避免"真楼本来就没进集合"的混淆。
        from shapely.geometry import Polygon
        min_x, min_y, max_x, max_y = cls.env.global_bounds   # (minx,miny,maxx,maxy) 四元组
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        s = 60.0                                   # 120 m 见方，足够大到线段必穿
        cls.geom = Polygon([(cx - s, cy - s), (cx + s, cy - s),
                            (cx + s, cy + s), (cx - s, cy + s)])
        cls.p_in = (cx - s * 3, cy)                # 楼外两侧
        cls.p_out = (cx + s * 3, cy)
        cls._orig_bbox = cls.env._high_buildings_bbox
        cls._orig_high = cls.env.high_buildings
        # ⚠ 必须把禁飞区摘掉：`_is_path_clear_uncached` 在楼之后还会问 `no_fly.path_blocked`
        # （environment.py:2097），而合成楼正好落在地图中心＝默认禁飞圆处 ⇒ 低阈值面会因
        # **另一个障碍**而 blocked，H1 就变成在测禁飞区而不是测高度阈值（本轮实测就是这样红的）。
        cls._orig_nofly = cls.env.no_fly
        cls.env.no_fly = _EmptyNoFly()

    @classmethod
    def tearDownClass(cls):
        cls.env._high_buildings_bbox = cls._orig_bbox
        cls.env.high_buildings = cls._orig_high
        cls.env.no_fly = cls._orig_nofly
        if cls._prev_toggle is None:
            os.environ.pop(_TOGGLE, None)
        else:
            os.environ[_TOGGLE] = cls._prev_toggle
        # ⚠ 必须还原**进程级**桶字典：本门每个面用一栋不同几何的楼 ⇒ 会往
        # `environment._PATH_CLEAR_BUCKETS`（容量 _PATH_CLEAR_BUCKET_MAX=4）里塞 7 个条目，
        # 触发它的 `.clear()` —— 而字母序靠后的 `test_server_guards.PathClearBucketFingerprintTests`
        # 正持有自己那个 base 桶并断言"几何还原后回到同一个桶"。本轮实测就是这样红了一条
        # 与本门无关的用例（单独跑 OK、同进程连跑 FAIL）。合成楼的判定结果不该外溢给别的门。
        cls._kernel._PATH_CLEAR_BUCKETS.clear()
        cls._kernel._PATH_CLEAR_BUCKETS.update(cls._orig_buckets)

    def _install(self, height, jitter=0.0):
        """把障碍集合换成"只有这一栋楼（可选平移 jitter 米）"，筛选交给被测对象自己做。

        ⚠ 第一版这里手写 `if height > 20` 决定楼进不进列表 ⇒ 门在测我自己的判断，
        变异面（摘掉阈值）实测照样绿。现在统一走 `_recompute_high_buildings`（environment.py:375+），
        阈值只有一份真源。

        ⚠ **jitter 是承重的**：`is_path_clear` 的结果桶按「楼数 + 各楼 wkt」取指纹
        （`environment.py:2037-2043`），而 H2/H3 刻意让几何不变、只改 height ⇒ 所有面命中同一个
        进程级桶，第一次算出的判定会被后面每个面复用，变异根本传不到断言（本轮实测：把规划器改成
        ">100 m 不挡路"后 H2/H3 仍报相同值）。所以**每个面用一栋略微平移（1 m，不影响穿/不穿结论）
        的楼**，让指纹互不相同；`SWARM_BALANCE_PATHCLEAR_CACHE=0` 只挡磁盘 load/store，挡不住内存桶。
        """
        geom = self.geom if not jitter else shapely_affine(self.geom, jitter)
        self.env._recompute_high_buildings([{"geometry": geom, "height": height}])
        self.env._probe_geom = geom
        self.env._path_clear_cache = None          # 实例级缓存也要清，否则读上一面的判定
        return len(self.env.high_buildings)

    def _clear(self, h, jitter=0.0):
        self._install(h, jitter)
        g = self.env._probe_geom
        minx, miny, maxx, maxy = g.bounds
        cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
        s = (maxx - minx) / 2.0
        return self.env.is_path_clear((cx - s * 3, cy), (cx + s * 3, cy))

    def test_h1_threshold_is_load_bearing(self):
        """H1：25 m 挡、15 m 不挡 ⇒ "height > 20 的二值阈值"确实在承重。"""
        self.assertFalse(self._clear(25.0, 0.0),
                         "[H1] 25 m 的楼没挡住穿它的直线 ⇒ 障碍集合不按 %s 筛，"
                         "则『二值高度阈值』这句对外口径是假的" % THRESHOLD_NOTE)
        self.assertTrue(self._clear(15.0, 9.0),
                        "[H1] 15 m 的楼仍然挡路 ⇒ 阈值不起作用（可能按面积或无条件全收），"
                        "那么『低于阈值的楼对航线透明』这句就不能说" )
        print("[H1] 同几何 25m=>blocked  15m=>clear ⇒ 阈值 %s 承重" % THRESHOLD_NOTE)

    def test_h2_height_magnitude_is_discarded(self):
        """H2：25 m 与 250 m 必须相同 ⇒ 模型里没有连续高度这个量。"""
        a, b = self._clear(25.0, 1.0), self._clear(250.0, 2.0)
        self.assertEqual(a, b,
                         "[H2] 楼高变化改变了可通行性 ⇒ 高度已参与三维判定，"
                         "§2.2『height 值此后不再出现』与总纲 §3.2 需重写")
        c = self._clear(25.0 * 10**6, 3.0)
        self.assertEqual((a, b), (c, c), "[H2] 极端高度出现第三种结果 ⇒ 存在未登记的分支")
        print("[H2] 25 / 250 / 2.5e7 m 判定完全相同 (%s) ⇒ 高度值被丢弃" % a)

    def test_h3_above_threshold_behaves_as_infinite_prism(self):
        """H3：过阈值后等价于无限高平面棱柱 —— 抬高不会变得更可通行。"""
        blocked_low = self._clear(21.0, 4.0)
        blocked_high = self._clear(1e9, 5.0)
        self.assertFalse(blocked_low, "[H3] 21 m 未进障碍集 ⇒ 阈值不在 20，本门口径需重测")
        self.assertFalse(blocked_high,
                         "[H3] 1e9 m 反而可通行 ⇒ 出现了『更高就不挡』的反向逻辑，"
                         "等价性说法不成立")
        print("[H3] 21 m 与 1e9 m 均 blocked ⇒ 过阈值即无限高二维棱柱")

    def test_h4_shipped_world_actually_has_both_classes(self):
        """H4：真实地图上两类建筑都必须存在，否则前三条是在空集合上自证。

        这是本门的分母：osmnx 可用时碰撞体只有 18 栋、fallback 时有 108 栋
        （见 docs/数据来源与可追溯性登记表.md 三节），而"有高度信息的楼"远多于 108。
        若某台机器上没有任何楼过阈值，H1/H3 就只是在对我造的合成楼说话 ⇒ 必须点名。
        """
        high = len(self.env.high_buildings)
        finite = sum(1 for b in self.env.buildings_with_height
                     if b.get("height") is not None and b["height"] == b["height"]) \
            if hasattr(self.env, "buildings_with_height") else None
        self.assertGreater(high, 0,
                           "[H4][NO_DENOMINATOR] 当前环境里 0 栋楼过 20 m 阈值 ⇒ 前三条只在合成楼上成立，"
                           "不能据此对外声称真实地图的行为")
        print("[H4] 真实地图进入障碍集合的楼=%d 栋（另有未过阈值者不计）⇒ 分母存在" % high)


if __name__ == "__main__":
    unittest.main()
