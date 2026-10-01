"""控制台服务层守卫测试：预热门、对比口径标注、OSM 缓存失效判定。

不依赖 httpx/TestClient（本环境未安装），直接调用被 @app.get 装饰的函数本体——
FastAPI 的路由装饰器返回原函数，因此可以当普通函数测。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import tempfile
import unittest
from pathlib import Path

# 依赖预检放在重导入之前：缺 fastapi/shapely 时本模块整体 skip 并写明该用哪个解释器，
# 而不是抛 ImportError 变成 `_FailedTest` 的 error —— 评审看到 traceback 会以为仿真坏了。
from console import _preflight

_preflight.require("fastapi", "shapely", "pandas", gated_in="console/test_server_guards.py")

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


class CompareDirectionSingleSourceTests(unittest.TestCase):
    """「哪些指标不判优」只允许有一份定义，且前端必须消费后端下发的那份。

    实际漂过的样子：experiments/reporting.py 已把 泊位利用率 / 机巢周转率 移出
    "越高越好"（泊位 1→2→4 时排队 359s→0→0、完成率上升，这两项却同向下跌），
    而 console/static/index.html 的对比表仍在给它们高亮"最优算法" ——
    同一份数据，实验报告说"不判"、网页说"这个算法最好"。
    """

    def test_api_exposes_the_authoritative_ambiguous_set(self):
        payload = server.compare()
        self.assertIn("direction_ambiguous", payload,
                      "/api/compare 不再下发方向不明确指标名单，前端只能自己猜")
        from experiments.reporting import DIRECTION_AMBIGUOUS
        self.assertEqual(sorted(payload["direction_ambiguous"]), sorted(DIRECTION_AMBIGUOUS),
                         "下发的名单与 experiments/reporting.py 的 DIRECTION_AMBIGUOUS 不一致")

    def test_frontend_consumes_it_instead_of_hardcoding(self):
        html = (Path(__file__).resolve().parents[1] / "console" / "static" / "index.html"
                ).read_text(encoding="utf-8")
        self.assertIn("direction_ambiguous", html,
                      "前端没再读 /api/compare 的名单，改回硬编码就会与报告漂移")
        self.assertIn("compareAmbiguous", html, "前端没有把名单用到判优上")
        # 关键：判优函数必须在关键词正则**之前**排除这些指标，否则 泊位利用率
        # 会因为不含"越小越好"关键词而被默认成"越高越好"。
        fn = html.split("compareBestRow()")[1].split("},")[0]
        self.assertIn("compareAmbiguous", fn, "compareBestRow 里没有做不判优短路")
        self.assertLess(fn.index("compareAmbiguous"), fn.index("lowerBetter"),
                        "短路写在 lowerBetter 之后等于没写：默认分支仍会把它们判成越高越好")


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

    def test_rows_report_source_file(self):
        """keep='last' 会让后读到的文件顶掉先读到的，每行必须能追溯到来源 CSV。"""
        payload = server.compare()
        if not payload["rows"]:
            self.skipTest("results/compare 下没有可用 CSV")
        for row in payload["rows"]:
            src = row["口径"].get("来源")
            self.assertIsInstance(src, str, "行 %s 缺来源标注" % row["算法"])
            self.assertTrue(src.endswith(".csv"), "来源应是 CSV 文件名: %r" % src)

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


class SeedValidationTests(unittest.TestCase):
    """Seed 越界必须是可读的 400，而不是没有说明的 500。"""

    def test_negative_and_oversized_seed_rejected_with_400(self):
        from fastapi import HTTPException

        for bad in (-5, -1, 2 ** 32, 2 ** 63):
            with self.assertRaises(HTTPException, msg="seed=%s 应被拒绝" % bad) as ctx:
                server.reset(server.ResetRequest(algorithm="ga", seed=bad))
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertIn("Seed", ctx.exception.detail)

    def test_boundary_seeds_accepted(self):
        # 0 与 2**32-1 是 numpy 允许的边界；这两个值过去会在 pso/ga/ortools 路径上 500 吗？
        # 不会——只有区间外才会。这里只断言不抛 400。
        from fastapi import HTTPException

        for ok in (0, 1, 100, 2 ** 32 - 1):
            try:
                server.reset(server.ResetRequest(algorithm="greedy", seed=ok))
            except HTTPException as exc:  # pragma: no cover
                self.fail("seed=%s 不应被拒: %s" % (ok, exc.detail))


class VendorAssetTests(unittest.TestCase):
    """本地前端依赖必须可被取到，且不能成为任意文件读取口。"""

    def test_serves_each_vendored_library(self):
        from fastapi.responses import FileResponse

        for name in server._VENDOR_FILES:
            resp = server.vendor(name)
            self.assertIsInstance(resp, FileResponse)
            self.assertTrue(Path(resp.path).exists(), "本地依赖缺失: %s" % name)
            self.assertGreater(Path(resp.path).stat().st_size, 10000)

    def test_rejects_unknown_and_traversal_names(self):
        from fastapi import HTTPException

        for bad in ("nope.js", "../../../etc/passwd", "server.py", ""):
            with self.assertRaises(HTTPException, msg="应拒绝: %r" % bad) as ctx:
                server.vendor(bad)
            self.assertEqual(ctx.exception.status_code, 404)


class CheckpointGenerationTests(unittest.TestCase):
    """rebuild 不再销毁快照，改为跨代拒绝恢复。"""

    @classmethod
    def setUpClass(cls):
        from console.sim_session import SimSession

        cls.session = SimSession()
        cls.session.reset(algorithm="greedy", seed=100)

    def test_saved_checkpoint_records_generation(self):
        self.session.save_checkpoint("gen-check")
        stored = self.session._checkpoints["gen-check"]
        self.assertEqual(stored["env_gen"], self.session._env_generation())
        self.assertTrue(self.session.list_checkpoints()[0]["可用"])

    def test_cross_generation_restore_is_refused_with_explanation(self):
        self.session.save_checkpoint("stale-check")
        original = self.session._checkpoints["stale-check"]["env_gen"]
        self.session._checkpoints["stale-check"]["env_gen"] = "000000000000"
        try:
            with self.assertRaises(ValueError) as ctx:
                self.session.load_checkpoint("stale-check")
            self.assertIn("环境重建", str(ctx.exception))
            rows = {r["name"]: r for r in self.session.list_checkpoints()}
            self.assertFalse(rows["stale-check"]["可用"])
        finally:
            self.session._checkpoints["stale-check"]["env_gen"] = original

    def test_rebuild_no_longer_destroys_checkpoints(self):
        """旧实现在 rebuild() 里 clear()，误点一次「保存并应用」就丢掉答辩前存的全部节点。
        这里锁住源码，防止有人为了「省事」把保护改回去。"""
        import inspect

        from console.sim_session import SimSession

        src = inspect.getsource(SimSession.rebuild)
        self.assertNotIn("_checkpoints.clear()", src)

    def test_save_reports_overwrite_and_eviction(self):
        """存满 5 个后再存，最旧的那个会被淘汰；同名则被覆盖。两者过去都静默。"""
        self.session._checkpoints.clear()
        last = None
        for i in range(1, 7):
            last = self.session.save_checkpoint("slot-%d" % i)
        self.assertEqual(last["淘汰"], "slot-1")
        self.assertIsNone(last["覆盖"])
        self.assertEqual(last["槽位"], "5/5")
        self.assertNotIn("slot-1", [c["name"] for c in last["checkpoints"]])

        again = self.session.save_checkpoint("slot-3")
        self.assertEqual(again["覆盖"], "slot-3")
        self.assertIsNone(again["淘汰"])
        self.assertEqual(again["槽位"], "5/5")

    def test_same_generation_restore_still_works(self):
        self.session.save_checkpoint("ok-check")
        snap = self.session.load_checkpoint("ok-check")
        self.assertIn("step", snap)


class SchedulerConfigWriteTests(unittest.TestCase):
    """调度器配置写盘：空 patch 不许动文件，真改动必须动文件。

    两半都要测。只测"空 patch 不该写"会给出假绿灯 —— 我第一版守卫写成
    `if _deep_merge(cfg, patch) != cfg`，而 _deep_merge 是原地改写 base 并返回
    同一对象，于是恒为假、把所有保存请求都吞掉了，空 patch 那侧照样"通过"。
    """

    def _tmp_yaml(self, td):
        src = pathlib.Path(server._ALG_YAML)
        dst = pathlib.Path(td) / "config.yaml"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        return dst

    def test_noop_patch_does_not_rewrite_the_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            dst = self._tmp_yaml(td)
            original = server._ALG_YAML
            server._ALG_YAML = dst
            try:
                before = dst.read_bytes()
                server.save_scheduler_config(server.ConfigPatch(patch={}))
                self.assertEqual(dst.read_bytes(), before,
                                 "空 patch 也重写了文件 —— safe_dump 会抹掉全部注释")
            finally:
                server._ALG_YAML = original

    def test_real_change_is_persisted(self):
        import tempfile, yaml
        with tempfile.TemporaryDirectory() as td:
            dst = self._tmp_yaml(td)
            original = server._ALG_YAML
            server._ALG_YAML = dst
            try:
                before = dst.read_bytes()
                server.save_scheduler_config(server.ConfigPatch(patch={"seed": 123}))
                self.assertNotEqual(dst.read_bytes(), before,
                                    "真改动没落盘 —— 守卫把该写的也挡了")
                self.assertEqual(yaml.safe_load(dst.read_text(encoding="utf-8")).get("seed"), 123)
            finally:
                server._ALG_YAML = original


class ConfigSignatureCacheTests(unittest.TestCase):
    """_env_generation 与 map_static 的记忆化必须"快但不 stale"。"""

    def test_signature_is_stable_then_tracks_file(self):
        import tempfile, time
        from config import config_loder as CL
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "sim.json"
            p.write_text('{"environment": {"num_drones": 10}}', encoding="utf-8")
            a = CL.config_signature(p)
            self.assertEqual(a, CL.config_signature(p), "同一文件同一状态下签名不该变")
            p.write_text('{"environment": {"num_drones": 11}}', encoding="utf-8")
            os.utime(p, ns=(time.time_ns(), time.time_ns()))
            self.assertNotEqual(a, CL.config_signature(p), "改过配置后签名没变，指纹缓存会永远 stale")

    def test_env_generation_cache_returns_same_value_as_cold(self):
        session = server._get_session()
        fresh = dict(session._GEN_CACHE)
        try:
            session._GEN_CACHE.clear()
            cold = session._env_generation()
            self.assertEqual(len(session._GEN_CACHE), 1, "冷算后应刚好落一条缓存")
            warm = session._env_generation()
            self.assertEqual(cold, warm, "缓存命中后指纹与冷算不一致")
        finally:
            session._GEN_CACHE.clear()
            session._GEN_CACHE.update(fresh)

    def test_map_static_is_memoized_but_rebuilt_for_a_new_env(self):
        session = server._get_session()
        first = session.map_static()
        self.assertIs(session.map_static(), first, "同一个 Environment 应复用同一份静态几何")
        src = session._map_static_src
        try:
            session._map_static_src = None   # 模拟 env 被换掉：身份校验应判定缓存失效
            second = session.map_static()
            self.assertIsNot(second, first, "env 换了还返回旧几何，就是 stale 缓存")
            self.assertIs(session.map_static(), second, "重算后应落到新缓存，而不是每次重建")
        finally:
            session._map_static_src = src


class CompletedTaskLogTests(unittest.TestCase):
    """任务生命周期视图曾恒空：快照读的是每步末尾就被 clear() 的临时缓冲。"""

    def test_catalog_reads_the_durable_log_not_the_scratch_buffer(self):
        env_src = (Path(server.__file__).resolve().parent.parent / "frontend" / "environment.py").read_text(encoding="utf-8")
        ses_src = (Path(server.__file__).resolve().parent / "sim_session.py").read_text(encoding="utf-8")
        # 临时缓冲确实还在被 clear —— 这正是当初视图恒空的根因
        self.assertIn("self.completed_tasks.clear()", env_src)
        self.assertIn('completed = list(getattr(self.env, "completed_task_log"', ses_src)
        self.assertNotIn('getattr(self.env, "completed_tasks"', ses_src)
        # 每一条进临时缓冲的行，都必须同时进耐久日志
        self.assertIn("self.completed_task_log.append(self.completed_tasks[-1])", env_src)
        # 日志必须有界（长跑不能无界增长，且检查点会 deepcopy 它）
        self.assertIn("if len(self.completed_task_log) > 120:", env_src)
        self.assertEqual(env_src.count("self.completed_task_log = []"), 2, "声明与 reset 各一处")


class PathClearBucketFingerprintTests(unittest.TestCase):
    """通行判定结果按几何指纹分桶共享，指纹漏掉任何输入都会导致跨环境穿模。"""

    def test_fingerprint_covers_no_fly_geometry_and_margin(self):
        env = server._get_session().env
        buckets = __import__("environment")._PATH_CLEAR_BUCKETS
        base = env._path_clear_bucket()
        z = env.no_fly.zones[0]
        old_geom, old_margin = z.geometry, z.margin
        try:
            from shapely.geometry import MultiPoint
            pts = list(z.raw.exterior.coords) + [(z.raw.centroid.x, z.raw.centroid.y + d) for d in (0, 1200)]
            z.geometry = MultiPoint(pts).convex_hull
            z.margin = 1200.0
            self.assertIsNot(env._path_clear_bucket(), base,
                             "禁飞区几何/余量变了却仍复用旧桶 —— 缓存会返回过期的通行判定")
        finally:
            z.geometry, z.margin = old_geom, old_margin
        self.assertIs(env._path_clear_bucket(), base,
                      "几何还原后应回到同一个桶（指纹必须是几何的纯函数）")
        self.assertLessEqual(len(buckets), __import__("environment")._PATH_CLEAR_BUCKET_MAX)


class EnvironmentResetCoverageTests(unittest.TestCase):
    """Environment.reset() 必须归零每一个按步累计的统计量。

    曾漏掉 6 个：控制台每点一次「重置」就叠加一轮，实测 avg_drone_utilization
    走成 1.0 → 2.0 → 3.0（利用率 300%，物理不可能），total_flight_distance 同步翻倍；
    而 empty_load_ratio 因为分子分母一起泄漏反而看不出异常。
    实验侧不受影响（worker 每 episode 新建 Environment），所以只有 Web 会话会踩。
    """

    _COUNTERS = (
        "drone_busy_steps", "total_flight_distance", "total_empty_distance",
        "total_loaded_distance", "total_no_fly_detours", "total_chain_insertions",
    )

    def test_accumulators_are_cleared_in_reset(self):
        src = (Path(server.__file__).resolve().parent.parent / "frontend" / "environment.py").read_text(encoding="utf-8")
        start = src.find("def reset(")
        self.assertGreater(start, 0)
        body = src[start:src.find("\n    def ", start + 10)]
        assigned = set(re.findall(r"self\.([A-Za-z_]\w*)\s*=", body))
        missing = [c for c in self._COUNTERS if c not in assigned]
        self.assertFalse(missing, f"Environment.reset() 漏归零: {missing}")

    def test_no_statistics_accumulator_escapes_reset(self):
        """通用不变式：凡是 get_statistics 读到的自增字段，reset() 里必须重新赋值。"""
        src = (Path(server.__file__).resolve().parent.parent / "frontend" / "environment.py").read_text(encoding="utf-8")
        start = src.find("def reset(")
        body = src[start:src.find("\n    def ", start + 10)]
        assigned = set(re.findall(r"self\.([A-Za-z_]\w*)\s*=", body))
        stats = src[src.find("def get_statistics("):]
        stats = stats[:stats.find("\n    def ", 10)]
        read = set(re.findall(r"self\.([A-Za-z_]\w*)", stats))
        bumped = set(re.findall(r"self\.([A-Za-z_]\w*)\s*\+=", src))
        leak = sorted((read & bumped) - assigned)
        self.assertFalse(leak, f"get_statistics 用到的自增量没在 reset() 归零: {leak}")


class FrontendGuardTests(unittest.TestCase):
    """锁住三个「点了没反应 / 静默覆盖」类前端缺陷的修复。

    这些是纯前端逻辑，本环境没有 JS 测试框架（也不该为几条断言引入），
    因此用源码断言防止被改回去——与 rebuild 不再 clear() 那条同一手法。
    """

    @classmethod
    def setUpClass(cls):
        cls.html = (Path(server._STATIC).read_text(encoding="utf-8"))

    def test_no_phantom_experiment_tab(self):
        # 实验区块在 tab==='compare' 模板内；把 tab 设成 'experiment' 会让整页空白
        self.assertNotIn("this.tab = 'experiment'", self.html)
        self.assertNotIn("async switchTabExperiment", self.html)
        # 进入算法层必须把预设与状态拉起来，否则下拉框恒空、下载按钮不出现
        self.assertIn("ensureExperimentData", self.html)

    def test_config_modal_cannot_save_unloaded_defaults(self):
        self.assertIn("configLoaded", self.html)
        self.assertIn("if (!this.configLoaded)", self.html)
        self.assertIn('!configLoaded', self.html)          # 保存按钮 disabled
        # 场景编辑器同一缺陷，同一修法
        self.assertIn("if (!this.sceneLoaded)", self.html)
        self.assertIn("!sceneLoaded", self.html)

    def test_stale_step_response_is_discarded(self):
        self.assertIn("if (seq !== this.stepSeq) return;", self.html)
        self.assertIn("this.stepSeq++", self.html)          # stopPlay 递增

    def test_sidebar_counts_do_not_read_phantom_keys(self):
        """侧栏两处数字曾读快照里根本不存在的键，于是恒为 0 且与地图自相矛盾。"""
        self.assertNotIn("low_battery_drones", self.html)
        self.assertNotIn("snap.no_fly_zones", self.html)
        self.assertIn("health?.critical_battery", self.html)
        self.assertIn("health?.no_fly_count", self.html)
        # 后端必须真的发这两个键
        src = (Path(__file__).resolve().parent / "sim_session.py").read_text(encoding="utf-8")
        self.assertIn('"no_fly_count": no_fly', src)
        # 低电阈值只能与计数同源；界面不许再自己写死百分数
        self.assertNotIn("&lt;30%", self.html)
        self.assertIn("batteryLowPct", self.html)
        # 计数与阈值同源，且走 sys.modules 取属性（drone 会被 reload，值绑定会留在旧值上）
        self.assertIn('getattr(sys.modules.get("drone"), "BATTERY_LOW_THRESHOLD"', src)
        self.assertNotIn(') < 0.2)', src)

    def test_algorithm_shown_is_the_one_running(self):
        """改下拉不会热切换调度器，所以展示必须读快照真值，否则界面在替用户撒谎。"""
        self.assertIn("runningAlgorithm() { return this.snap.algorithm || this.algorithm; }", self.html)
        self.assertIn("pendingAlgorithm()", self.html)
        self.assertIn("算法 <b>{{ runningAlgorithm.toUpperCase() }}</b>", self.html)
        self.assertIn("当前调度策略</div><div class=\"v\">{{ runningAlgorithm.toUpperCase() }}", self.html)
        # 待生效必须显式标出来，不能让人以为已经切换了
        self.assertIn('class="pend"', self.html)

    def test_episode_end_is_visible_and_buttons_honest(self):
        self.assertIn('@click="togglePlay" :disabled="snap.done"', self.html)
        self.assertIn("playing || stepping || snap.done", self.html)
        self.assertIn("本回合已结束", self.html)

    def test_legend_carries_color_and_shape_on_one_glyph(self):
        """色块永远是圆的，旁边的文字却写 ◆/■/▼ —— 圆点与自己的文字矛盾。"""
        self.assertNotIn('<i class="dot" style="background:var(--idle)"', self.html)
        self.assertGreaterEqual(self.html.count('<i class="lg" style="color:var('), 5)
        self.assertIn(".legend .lg {", self.html)

    def test_disabled_and_focus_styles_cover_the_small_buttons(self):
        # 引入这条断言时（c819118）`console/static/index.html` 里有一批 `:disabled` 落在
        # `.tiny-btn` 上、而样式只写了 `.btn` ⇒ 禁用后外观不变。
        # 现在有几处不在这里记数：`grep -ac ':disabled' console/static/index.html` 一行就是现数。
        self.assertIn(".tiny-btn:disabled", self.html)
        # 焦点环曾是旧主题的钴蓝，贴在绿色品牌上
        self.assertNotIn("#1d4ed8", self.html)
        self.assertIn("[tabindex]:focus-visible { outline: 2px solid var(--accent-ink)", self.html)


class PathClearCacheTests(unittest.TestCase):
    """is_path_clear 的结果缓存必须给出与重算完全一致的答案。"""

    @classmethod
    def setUpClass(cls):
        from console.sim_session import SimSession

        cls.session = SimSession()
        cls.session.reset(algorithm="greedy", seed=100)
        cls.env = cls.session.env

    def test_cached_answer_equals_uncached(self):
        drones = self.env.drones
        pairs = [((a.x, a.y), (b.x, b.y)) for a, b in zip(drones, drones[1:])]
        self.assertTrue(pairs)
        for p1, p2 in pairs:
            with_cache = self.env.is_path_clear(p1, p2)
            self.env._path_clear_cache.clear()
            without = self.env._is_path_clear_uncached(tuple(p1), tuple(p2))
            self.assertEqual(with_cache, without, "缓存改变了判定: %s->%s" % (p1, p2))

    def test_second_call_hits_cache_without_growing_it(self):
        p1, p2 = (self.env.drones[0].x, self.env.drones[0].y), (self.env.drones[1].x, self.env.drones[1].y)
        self.env.is_path_clear(p1, p2)
        size = len(self.env._path_clear_cache)
        self.assertGreater(size, 0)
        self.env.is_path_clear(p1, p2)
        self.assertEqual(len(self.env._path_clear_cache), size, "重复查询不应新增条目（即应命中缓存）")

    def test_list_arguments_are_accepted(self):
        # 调用方可能传 list；缓存键必须转成 tuple，否则 TypeError: unhashable
        p1 = [self.env.drones[0].x, self.env.drones[0].y]
        p2 = [self.env.drones[1].x, self.env.drones[1].y]
        self.assertIsInstance(self.env.is_path_clear(p1, p2), bool)

    def test_cache_is_not_deep_copied_into_checkpoints(self):
        from console.sim_session import SimSession

        self.assertIn("_path_clear_cache", SimSession._CHECKPOINT_STATIC_ENV_KEYS)
        self.assertIn("_high_buildings_bbox", SimSession._CHECKPOINT_STATIC_ENV_KEYS)


class StepSecondsDeclarationTests(unittest.TestCase):
    """规范 WL-1.2：步长→秒的映射必须是代码常量并在 UI 声明，不能只靠配置凑自洽。"""

    def test_clock_advances_by_the_constant(self):
        from console.sim_session import SimSession
        from drone import STEP_SECONDS

        s = SimSession()
        s.reset(algorithm="greedy", seed=100)
        s.step_many(7)
        self.assertAlmostEqual(s.env.current_time, 7 * STEP_SECONDS, places=6)

    def test_meta_exposes_the_mapping(self):
        value = server.meta()["step_seconds"]
        self.assertGreater(float(value), 0.0)

    def test_ui_states_the_mapping(self):
        html = Path(server._STATIC).read_text(encoding="utf-8")
        self.assertIn("1 步 = ", html)
        self.assertIn("step_seconds", html)


class ReleaseCheckOutputCaptureTests(unittest.TestCase):
    """release_check 的失败诊断不能被子进程编码问题吃掉。

    Windows 上 subprocess(text=True) 按父进程 locale（cp936）解码，而子进程在
    PYTHONUTF8 下输出 UTF-8（或反过来），reader 线程会 UnicodeDecodeError 死掉、
    stdout 变 None —— 于是 `if not ok and out` 拿不到任何原因，闸门 FAIL 却不说话。
    """

    def test_failure_detail_is_captured_even_with_chinese_output(self):
        import subprocess
        import sys as _sys
        from pathlib import Path as _P

        root = _P(__file__).resolve().parents[1]
        sys_path = str(root)
        if sys_path not in _sys.path:
            _sys.path.insert(0, sys_path)
        import release_check

        src = (
            "import sys\n"
            "sys.stderr.write('断言失败：机巢泊位数不一致 中文诊断\\n')\n"
            "sys.exit(1)\n"
        )
        with tempfile.TemporaryDirectory() as td:
            child = _P(td) / "failchild.py"
            child.write_text(src, encoding="utf-8")
            ok, out = release_check._run([_sys.executable, str(child)])
        self.assertFalse(ok, "子进程应当以非零码退出")
        self.assertIn("断言失败：机巢泊位数不一致", out,
                      "失败诊断文本必须被捕获，否则闸门 FAIL 时无法定位原因")


if __name__ == "__main__":
    unittest.main()
