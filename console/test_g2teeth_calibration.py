# -*- coding: utf-8 -*-
"""#70-P1 阶段②：g2teeth 重标定 —— PSO buffer 触发口的**已知标签**夹具（常驻门）。

## 为什么要有这个文件（旧门的死法）
旧 g2teeth 把"门的牙"挂在 **真实工况下 size 触发口会打开**（`flush_size>0`）上。
D-iv 修好 completion 计时后，同一工况 `flush_size=0 / buffer_peak=10` ⇒ 判据不可满足 = 永红夹具，
只能显式 skip `[GATE_CALIBRATION_STALE]`（#69-H3 裁定①）。根因不是算法坏了，是**命题选错层**：
拿"一次特定运行的读数"当结构判据，业务语义一变就作废，且永远分不清"算法没积压"与"我测错了"。

## 本文件的改性（两层，各走各的通道）
  L1 机制层（=本门，常驻、进退码）：**手工构造 buffer 长度已知的场景**，断言 size 触发口
     在阈值 ±1 两侧行为正确，并证明 emergency / timeout 两个口不冒充 size。
     ⇒ 标签来自**我们自己写死的输入 + 配置常数本身**，零依赖任何正式实验。
  L2 观测层（真实工况读数）：住在常驻门
     console/test_speed_fallback_gate.py::test_g2teeth_mutation_turns_the_denominator_off
     里，形状是**一条 print 行 `[G2TEETH_L2_OBSERVED]`，不是用例**；只作信息报出、不进退码——
     因为"当前计时下真实工况积压不到 15"是 scheduler 行为事实，不是实现缺陷（#69-H3 裁定②）。
     它升为判据的三个前置条件（阈值推导入库 / 场景契约固定 / 变异两面各配证人）写在
     docs/P70_g2teeth_calibration_plan.md §8。本文件 8 条全是 L1。

## 硬约束（主控原话）
  · **不得拿 phase1b1 正式配对实验的结果当标定依据**（那是待验对象不是标尺）⇒
    本文件不 import experiments/、不读 results/ 下任何产物；所有期望值由 §LABELS 里的推导给出。
  · 不动阈值、不动 scheduler 语义（改它们属另一类授权）。
  · 转成真实判定前必须两面归档：先红（变异面 K6 必须咬）后绿（清洁树全绿）。

## LABELS —— 每条期望值的来源（不是"看当前读数定"）
| 夹具 | 输入（写死） | 期望 | 标签从何而来 |
|---|---|---|---|
| K1 | N=THRESHOLD-1, 无紧急, t=10 | flush_size==0 且三口皆 0 | 比较式 `len(buffer) >= threshold`（pso_scheduler.py:1444）：THRESHOLD-1 < THRESHOLD |
| K2 | N=THRESHOLD,   无紧急, t=10 | flush_size==1 | 同上：等号成立（`>=` 而非 `>`） |
| K3 | N=THRESHOLD+1, 无紧急, t=10 | flush_size==1（**不是 2**） | `_maybe_flush_buffer` 每步至多一个 reason（reason 单赋值 + 末尾单次计数 :1618） |
| K4 | N=THRESHOLD-1, 有紧急, t=10 | flush_emergency==1 且 flush_size==0 | 归因互斥：size 分支先判、不成立才落 emergency（:1444→:1446-1455） |
| K5 | N=THRESHOLD-1, 无紧急, t=THRESHOLD_TIME | flush_timeout==1 且 flush_size==0 | 同上：timeout 分支只在 reason is None 时求值（:1456-1460） |
| K6 | 同 K2 但把源码 `>=` 改成 `>`（临时副本） | K2 **必须变红**、K1 仍绿 | 这是整套 L1 的牙；不咬则标定作废 |
阈值三个常数一律**从被测对象自己的配置里读**（不抄字面量）：
`PSOScheduler.buffer_size_threshold / emergency_ttl / buffer_timeout` ← `backend_si/config.yaml:dual_channel`。
短码：[CAL_NO_TEETH] / [CAL_LABEL_SOURCE_LEAK] / [CAL_FROZEN_DRIFT] / [CAL_BLIND]
退出码：任一夹具不符=1。参与 discover（常驻门）。
"""
from __future__ import annotations

import ast
import hashlib
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "frontend")]

#: 冻结三元组之"版本"：这三个生产文件任一哈希变化 ⇒ calibration 必须重开（见 test_freeze_triple）。
FROZEN_PRODUCTION_FILES = (
    "backend_si/pso_scheduler.py",
    "frontend/environment.py",
    "frontend/drone.py",
)
#: 冻结三元组之"阈值来源"
THRESHOLD_SOURCE = "backend_si/config.yaml:dual_channel.{buffer_size_threshold,emergency_ttl,buffer_timeout}"
#: 冻结三元组之"夹具集合"
FIXTURE_SET = ("K1_below", "K2_at", "K3_above_once", "K4_emergency_not_size",
               "K5_timeout_not_size", "K6_mutation_ge_to_gt")


def _make_scheduler(seed=7):
    """构造一个**未跑过任何环境**的 PSOScheduler：只用它的运行时状态与触发口代码。

    刻意不起 Environment / 不读 OSM ⇒ 秒级、可重复、与被测实验完全解耦。
    """
    from backend_si.pso_scheduler import PSOScheduler
    return PSOScheduler(num_drones=2, verbose=False, seed=seed)


def _task(i, deadline=float("inf")):
    return {"task_id": "t%d" % i,
            "source": (100.0 * i, 0.0), "destination": (100.0 * i + 50.0, 50.0),
            "priority": 3, "weight": 1.0, "_abs_deadline": deadline}


def _obs():
    return {"drone_positions": [(0.0, 0.0), (10.0, 0.0)], "charging_stations": None}


def _fill(sched, n, deadline=float("inf"), entry_time=0.0):
    sched.pending_buffer = [_task(i, deadline) for i in range(n)]
    sched.buffer_entry_time = {"t%d" % i: entry_time for i in range(n)}


def _flush_counts(sched):
    return {k: int(sched.stats.get(k, 0))
            for k in ("flush_size", "flush_emergency", "flush_timeout")}


class BufferTriggerCalibration(unittest.TestCase):
    """L1 机制层：size 触发口在阈值 ±1 两侧的行为，以及三口归因互不污染。"""

    @classmethod
    def setUpClass(cls):
        s = _make_scheduler()
        cls.TH = int(s.buffer_size_threshold)
        cls.TTL = float(s.emergency_ttl)
        cls.TO = float(s.buffer_timeout)
        # 标签来源自检：三个数必须真的来自被测对象的配置，而不是我在测试里写的字面量
        cfg_src = (ROOT / "backend_si" / "config.yaml").read_text(encoding="utf-8")
        for name, val in (("buffer_size_threshold", cls.TH), ("emergency_ttl", cls.TTL),
                          ("buffer_timeout", cls.TO)):
            m = re.search(r"%s:\s*([0-9.]+)" % name, cfg_src)
            assert m and float(m.group(1)) == val, \
                "[CAL_LABEL_SOURCE_LEAK] %s 与 config.yaml 不一致（%s vs %s）⇒ 标签来源被换掉了" % (
                    name, val, m.group(1) if m else "缺失")

    # ---------------- K1 / K2 / K3：边界两侧 ----------------
    def test_K1_below_threshold_does_not_fire(self):
        s = _make_scheduler()
        _fill(s, self.TH - 1)
        s._maybe_flush_buffer(_obs(), current_time=10.0)
        c = _flush_counts(s)
        self.assertEqual(c["flush_size"], 0,
                         "[CAL_K1] N=%d < 阈值 %d 却打开了 size 口：%s" % (self.TH - 1, self.TH, c))
        self.assertEqual(sum(c.values()), 0,
                         "[CAL_K1] 无紧急、未到 timeout 的 N=%d 场景不该有任何 flush，实得 %s ⇒ "
                         "夹具不干净（标签就不成立了）" % (self.TH - 1, c))

    def test_K2_at_threshold_fires_exactly_once(self):
        s = _make_scheduler()
        _fill(s, self.TH)
        s._maybe_flush_buffer(_obs(), current_time=10.0)
        c = _flush_counts(s)
        self.assertEqual(c["flush_size"], 1,
                         "[CAL_K2] N=%d == 阈值 %d 应恰好开一次 size 口，实得 %s（判据来自 `>=` 含等号）" % (
                             self.TH, self.TH, c))

    def test_K3_above_fires_once_not_twice(self):
        s = _make_scheduler()
        _fill(s, self.TH + 1)
        s._maybe_flush_buffer(_obs(), current_time=10.0)
        c = _flush_counts(s)
        self.assertEqual(c["flush_size"], 1,
                         "[CAL_K3] 一步内 reason 只有一个值（:1442-1460 是 if/if-is-None 链），"
                         "N=%d 也只该计 1 次；实得 %s ⇒ 计数点被改了或本夹具理解错了形状" % (
                             self.TH + 1, c))

    # ---------------- K4 / K5：归因互斥 ----------------
    def test_K4_emergency_is_attributed_to_emergency_not_size(self):
        s = _make_scheduler()
        _fill(s, self.TH - 1, deadline=10.0 + self.TTL - 1.0)   # 剩余 TTL < emergency_ttl
        s._maybe_flush_buffer(_obs(), current_time=10.0)
        c = _flush_counts(s)
        self.assertEqual((c["flush_size"], c["flush_emergency"]), (0, 1),
                         "[CAL_K4] 紧急场景必须记在 flush_emergency 上、不得冒领 size：%s" % c)

    def test_K5_timeout_is_attributed_to_timeout_not_size(self):
        s = _make_scheduler()
        _fill(s, self.TH - 1, entry_time=0.0)
        s._maybe_flush_buffer(_obs(), current_time=self.TO + 80.0)   # 滞留 > buffer_timeout
        c = _flush_counts(s)
        self.assertEqual((c["flush_size"], c["flush_timeout"]), (0, 1),
                         "[CAL_K5] 超时场景必须记在 flush_timeout 上、不得冒领 size：%s" % c)

    # ---------------- K6：这套夹具的牙 ----------------
    def test_K6_mutation_of_the_comparison_turns_K2_red(self):
        """变异面：把 `len(pending_buffer) >= threshold` 改成 `>` ⇒ K2 必须变红、K1 仍绿。

        ⚠ 不改生产文件：复制整个仓不需要，只把 pso_scheduler.py 抄进临时目录、
          改那一行、用 PYTHONPATH 前置让 `import backend_si...` 命中副本？——不行，
          它是包内模块。⇒ 改用**运行时 monkeypatch 等价物**：直接对被测实例覆写同一个谓词
          （见 `_fire_with_strict_gt`），它与源码 `>` 的差别只在边界那一格，正是本面要照的地方。
        """
        strict_gt = lambda n, th: n > th           # 变异后的比较式
        k2 = strict_gt(self.TH, self.TH)           # 变异后 N==阈值 不再触发 ⇒ K2 应失配
        k1 = strict_gt(self.TH - 1, self.TH)
        self.assertFalse(k2, "[CAL_NO_TEETH] 变异式仍让 N==阈值触发 ⇒ 本面测不到任何东西")
        self.assertFalse(k1, "[CAL_BLIND] 变异式连 N<阈值 都不触发 ⇒ 变异范围过大，不能当牙")
        # 关键一步：真跑一遍"变异语义"下的 K2 场景，确认我们的**断言**会因此变红
        # （即把 flush 判定换成严格大于后，flush_size 应为 0，而 K2 断言要求 1）
        s = _make_scheduler()
        _fill(s, self.TH)
        orig_th = s.buffer_size_threshold
        s.buffer_size_threshold = orig_th + 1      # 等价于把 `>=T` 变成 `>T`（对整数 N 完全同形）
        try:
            s._maybe_flush_buffer(_obs(), current_time=10.0)
        finally:
            s.buffer_size_threshold = orig_th
        c = _flush_counts(s)
        self.assertEqual(c["flush_size"], 0,
                         "[CAL_NO_TEETH] 把阈值抬到 T+1（等价于 `>=`→`>`）后 size 口仍开 ⇒ "
                         "K2 没有牙，整套标定不可信：%s" % c)
        print("[CAL_TEETH] 变异面生效：阈值 +1（≡`>=`→`>`）使 N==%d 从 flush_size=1 变 0；K1 不受影响" % self.TH)

    # ---------------- 冻结三元组 ----------------
    def test_freeze_triple_is_recorded_and_recomputable(self):
        """标定完成即冻结：阈值来源 + 夹具集合 + 版本（生产文件哈希）。

        这一条**不锁死哈希**（锁死会让每次正常改动都变红、逼人放宽）；它做的是：
          · 当场算出三个哈希并印出来 ⇒ 任何人可复算、可与文档比对；
          · 断言 `pso_scheduler.py` 里那两处承重位置仍然在位（比较式 + 计数点），
            若被改名/删除，哈希漂了也没人知道 ⇒ 这条比哈希更硬。
        """
        h = {}
        for rel in FROZEN_PRODUCTION_FILES:
            p = ROOT / rel
            self.assertTrue(p.is_file(), "[CAL_BLIND] 冻结清单里的文件不存在：%s" % rel)
            h[rel] = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        src = (ROOT / "backend_si" / "pso_scheduler.py").read_text(encoding="utf-8")
        cmp_pat = re.search(r"len\(self\.pending_buffer\)\s*>=\s*self\.buffer_size_threshold", src)
        cnt_pat = re.search(r"self\.stats\[f'flush_\{reason\}'\]\s*\+=\s*1", src)
        self.assertIsNotNone(cmp_pat,
                             "[CAL_FROZEN_DRIFT] 找不到 size 触发口的比较式（原 :1444）⇒ "
                             "承重语句被改名/移动，本文件的标签推导全部失效，须重开 calibration")
        self.assertIsNotNone(cnt_pat,
                             "[CAL_FROZEN_DRIFT] 找不到 flush 原因计数点（原 :1618）⇒ 夹具吃的计数器不再是权威证人")
        print("[CAL_FROZEN] version=threshold@%s fixtures=%s hashes=%s" % (
            THRESHOLD_SOURCE, ",".join(FIXTURE_SET),
            ";".join("%s=%s" % (k.split("/")[-1], v) for k, v in sorted(h.items()))))

    def test_no_experiment_artifacts_are_read(self):
        """硬约束自证：本门不得**读**正式配对实验产物（那是待验对象，不是标尺）。

        判据形状 = 只查"会真的打开文件 / 真的引入那个包"的构造，不查文本里出现过哪些词：
          · `open(...)` / `Path(...).read_*` / `json.load` 的参数若为字符串常量且指向
            results|experiments|paper → 红；
          · `import experiments...` 之类 → 红。
        ⚠ 前两版按文本 grep 禁词 ⇒ 被自己陈述规矩的 docstring、以及那张禁词表本身命中
          （四个 token 全中、门永远红）。那是量具形状错，不是现场违规 —— 同一条教训在 P2/P3
          门上已踩过两次：**判据必须认得自己扫的是什么**。宁可判据窄到"只测文件访问"，
          也不要一扇只会红的门；标签来源的正向证人另有两条：setUpClass 核三个常数与
          config.yaml 逐字相等、K1–K5 的期望值全部由阈值 ±1 推导（见 LABELS 表）。
        """
        tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
        offenders = []

        def const_str(node):
            return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None

        for node in ast.walk(tree):
            # ① import 侧：不许把 experiments/ 包引进来
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "experiments":
                    offenders.append("import-from:%s" % node.module)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] == "experiments":
                        offenders.append("import:%s" % a.name)
            # ② 调用侧：只有第一个参数是字面量时才可能指向实验产物目录
            elif isinstance(node, ast.Call):
                f = node.func
                fname = getattr(f, "attr", None) or getattr(f, "id", None)
                if fname in ("read_text", "open", "load", "read_bytes", "glob", "rglob"):
                    for arg in node.args[:1]:
                        s = const_str(arg)
                        if s and re.search(r"""(^|/)(results|experiments|paper)\b""", s):
                            offenders.append("%s(%r)" % (fname, s))
        self.assertEqual(offenders, [],
                         "[CAL_LABEL_SOURCE_LEAK] 标定门真的打开了正式实验产物或引入了 experiments 包：%s "
                         "⇒ 标签必须来自合成输入或配置常数" % offenders)
        # 正向证人：跑一遍真实读取路径，确认本门唯一依赖的外部文件是 config.yaml
        cfg = ROOT / "backend_si" / "config.yaml"
        self.assertTrue(cfg.is_file(), "[CAL_BLIND] 阈值来源文件不存在：%s" % cfg)
        print("[CAL_ISOLATION] AST 扫描：文件访问型违规=%d，import 型违规=0；唯一外部依赖=%s" % (
            len(offenders), cfg.relative_to(ROOT)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
