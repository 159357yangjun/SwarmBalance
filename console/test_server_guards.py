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
    """/api/compare 必须标出评测规模与基准不一致的算法，且不得改动数值。"""

    def test_flags_off_basis_rows_without_changing_values(self):
        import csv

        payload = server.compare()
        if not payload["rows"]:
            self.skipTest("results/compare 下没有可用 CSV")

        self.assertIn("basis", payload)
        self.assertIn("inconsistent", payload)
        for row in payload["rows"]:
            self.assertIn("口径", row)
            self.assertIsInstance(row["口径"]["偏离"], bool)

        flagged = {i["算法"] for i in payload["inconsistent"]}
        self.assertEqual(flagged, {r["算法"] for r in payload["rows"] if r["口径"]["偏离"]})

        # 数值必须与源 CSV 的最后一行一致：守卫只做标注，不参与计算。
        ga_path = server._PROJECT_ROOT / "results" / "compare" / "backend_ga_metrics.csv"
        if ga_path.exists():
            with ga_path.open(encoding="utf-8-sig", newline="") as fh:
                last = list(csv.DictReader(fh))[-1]
            ga_row = next((r for r in payload["rows"] if r["算法"] == last["算法"]), None)
            if ga_row is not None:
                self.assertAlmostEqual(float(last["完成率"]), ga_row["完成率"], places=4)


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
