"""控制台服务层守卫测试：预热门、对比口径标注、OSM 缓存失效判定。

不依赖 httpx/TestClient（本环境未安装），直接调用被 @app.get 装饰的函数本体——
FastAPI 的路由装饰器返回原函数，因此可以当普通函数测。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import console.server as server
from frontend.tools import osm


class SnapshotWarmingGateTests(unittest.TestCase):
    """预热门只在「后台线程还在跑」时生效，绝不能把请求卡死。"""

    def setUp(self):
        self._session = server._session
        self._done = server._warm_done.is_set()

    def tearDown(self):
        server._session = self._session
        if self._done:
            server._warm_done.set()
        else:
            server._warm_done.clear()

    def test_returns_202_while_session_is_building(self):
        server._session = None
        server._warm_done.clear()
        resp = server.snapshot()
        self.assertEqual(resp.status_code, 202)
        self.assertTrue(json.loads(resp.body)["warming"])

    def test_gate_opens_after_warm_thread_finishes(self):
        # 预热失败时 _warm_done 也会置位（见 _warm 的 finally），此时必须放行，
        # 让首个请求按老路径重试初始化，而不是让前端永远轮询 202。
        server._session = None
        server._warm_done.set()
        self.assertIsNone(server._warming_response())

    def test_gate_inactive_when_session_exists(self):
        server._warm_done.clear()
        server._session = object()  # 只要非 None 即代表已就绪
        self.assertIsNone(server._warming_response())


class CompareBasisTests(unittest.TestCase):
    """/api/compare 按「生成任务数」判定口径，且不得改动任何数值。"""

    def test_rows_carry_basis_metadata_without_changing_values(self):
        payload = server.compare()
        if not payload["rows"]:
            self.skipTest("results/compare 下没有可用 CSV")

        self.assertIn("basis", payload)
        self.assertIn("inconsistent", payload)
        for row in payload["rows"]:
            self.assertIn("口径", row)
            self.assertIsInstance(row["口径"]["偏离"], bool)
            rate = row.get("完成率")
            self.assertTrue(rate is None or 0.0 <= rate <= 1.0, "完成率越界: %r" % rate)

        flagged = {i["算法"] for i in payload["inconsistent"]}
        self.assertEqual(flagged, {r["算法"] for r in payload["rows"] if r["口径"]["偏离"]})

    def test_step_count_difference_alone_is_not_a_basis_violation(self):
        """总步数是 episode 提前结束的运行结果，同条件下各算法天然不同；
        只有分母（生成任务数）不一致才算口径问题。早先用 (总步数, 生成任务数)
        当复合基准时，10 行步数互不相等会让众数退化成无意义的 858 并误报 9 行。"""
        payload = server.compare()
        rows = payload["rows"]
        if not rows:
            self.skipTest("results/compare 下没有可用 CSV")
        tasks = {r["口径"]["生成任务数"] for r in rows}
        steps = {r["口径"]["总步数"] for r in rows}
        if len(tasks) == 1 and len(steps) > 1:
            self.assertEqual(payload["basis"], {"生成任务数": next(iter(tasks))})
            self.assertEqual(payload["inconsistent"], [], "仅步数不同不应被判为口径偏离")

    def test_no_common_basis_is_not_fabricated(self):
        """生成任务数各行都不一样时，宁可不给基准，也不硬选一个误导人。"""
        rows = [{"算法": a, "总步数": s, "生成任务数": n, "完成率": 1.0}
                for a, s, n in [("x", 900, 30), ("y", 2000, 60), ("z", 1200, 90)]]
        basis, inconsistent = server._resolve_basis(rows)
        self.assertIsNone(basis)
        self.assertEqual(inconsistent, [])


class OsmCacheKeyTests(unittest.TestCase):
    """缓存键必须随源文件指纹变化，坏缓存必须当作未命中。"""

    def test_key_changes_with_size_and_mode(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "a.osm"
            f.write_bytes(b"<osm></osm>")
            base = osm._cache_path(f, "osmnx")
            self.assertEqual(base.name, osm._cache_path(f, "osmnx").name)
            self.assertNotEqual(base, osm._cache_path(f, "fallback"))
            f.write_bytes(b"<osm></osm><extra/>")
            self.assertNotEqual(base, osm._cache_path(f, "osmnx"))

    def test_unreadable_source_disables_caching(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(osm._cache_path(Path(td) / "missing.osm", "osmnx"))

    def test_corrupt_or_missing_cache_is_a_miss(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "osm-bad.pkl"
            bad.write_bytes(b"definitely not a pickle")
            self.assertIsNone(osm._read_cache(bad))
            self.assertIsNone(osm._read_cache(Path(td) / "osm-missing.pkl"))

            truncated = Path(td) / "osm-shape.pkl"
            import pickle

            truncated.write_bytes(pickle.dumps(({"a": []}, [])))  # 建筑为空 → 视为未命中
            self.assertIsNone(osm._read_cache(truncated))


if __name__ == "__main__":
    unittest.main()
