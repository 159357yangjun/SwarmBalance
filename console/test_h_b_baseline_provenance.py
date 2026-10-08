# -*- coding: utf-8 -*-
"""(b) 基线溯源门：把 seed40907 avg_delay=2.802632 从"文档正文里的口头数"钉成可复算断言。

为什么建它：#69-H2 验收 (b) 要求"seed40907 冻结回放含 avg_delay=2.802632 逐字不变"，
但主控核基线时发现该数一度 grep 不到 ⇒ 必须先查清它是**有源头的产物**还是**口头读数**。
一手来源已定位到 `docs/取证输出/c1_paired_replay_f654587_fixed.json`（git 跟踪、引入于 aa75b5b #69-C1）
的 `metrics.mean_delay.{before,after}`。本门读那个字段并断言，使 (b) 的参照数不再依赖任何人引用文档正文。

三面（判别式，先红后绿都留档）：
  green —— 读真产物文件：before==after==2.802632 且 delta==0 ⇒ 通过；
  red   —— 变异面：把 mean_delay.after 改成 2.776316（即 H2 线段谓词实测值）写临时副本，
           断言必须报错 ⇒ 证明这扇门真的会拦下"基线被动了"的情形（不是永绿的摆设）；
  tracked —— 校验源文件确在 git 版本控制内且工作树未被改动（HEAD blob == hash-object），
           否则"冻结证人"可能只活在某个人的临时目录里。

短码（GBK 控制台下中文会变 ??????，判定信息一律带 ASCII 码）：
    [B_PROVENANCE_OK]        三面对账全过
    [B_FILE_MISSING]         源产物文件不存在
    [B_NOT_TRACKED]          源文件不在 git 跟踪内（口头数的风险来源）
    [B_WORKTREE_DRIFT]       工作树副本与 HEAD blob 不一致（被改过）
    [B_BASELINE_MOVED]       before != after 或 != 2.802632（冻结证人不再成立 → (b) 需重裁）
    [B_MUTATE_NOT_CAUGHT]    变异面没报错 ⇒ 门无牙（比没有更坏）
退出码：全过=0；任一硬失败=1。这是【读数+对账】型门，不参与论文判优。
"""
from __future__ import annotations
import json, os, pathlib, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTIFACT_REL = "docs/取证输出/c1_paired_replay_f654587_fixed.json"
ARTIFACT = ROOT / ARTIFACT_REL
BASELINE = 2.802632            # 六舍五入后的冻结读数
MUTANT_VALUE = 2.776316         # H2 线段谓词实测值：用来验证门会红


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class BaselineProvenance(unittest.TestCase):
    def test_A_green_real_artifact(self):
        """green：真产物文件的 mean_delay.before/after 都是 2.802632、delta=0、口径三元组对得上。"""
        if not ARTIFACT.is_file():
            self.fail(f"[B_FILE_MISSING] {ARTIFACT_REL}")
        d = _load(ARTIFACT)
        md = d["metrics"]["mean_delay"]
        self.assertAlmostEqual(md["before"], BASELINE, places=6,
                               msg=f"[B_BASELINE_MOVED] before={md['before']}≠{BASELINE}")
        self.assertAlmostEqual(md["after"], BASELINE, places=6,
                               msg=f"[B_BASELINE_MOVED] after={md['after']}≠{BASELINE}")
        self.assertEqual(md["delta"], 0.0, "[B_BASELINE_MOVED] C1 配对回放里 mean_delay 不该有 delta")
        # 口径三元组：这串数只在 seed/steps/algorithm 都对时才可比
        self.assertEqual((d["seed"], d["steps"], d["algorithm"]), (40907, 1200, "greedy"),
                         "[B_BASELINE_MOVED] 产物的 seed/steps/algorithm 与 (b) 口径不符")

    def test_B_mutation_has_teeth(self):
        """red：把 after 改成 H2 实测值写临时副本，同一判据必须报错——证明门会拦'基线被动'。"""
        if not ARTIFACT.is_file():
            self.skipTest("[B_FILE_MISSING] 无源文件，变异面无从构造")
        d = _load(ARTIFACT)
        d["metrics"]["mean_delay"]["after"] = MUTANT_VALUE
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        try:
            json.dump(d, tmp, ensure_ascii=False); tmp.close()
            md = _load(tmp.name)["metrics"]["mean_delay"]
            caught = False
            try:
                self.assertAlmostEqual(md["before"], md["after"], places=6)
                self.assertAlmostEqual(md["after"], BASELINE, places=6)
            except AssertionError:
                caught = True
            self.assertTrue(caught,
                            f"[B_MUTATE_NOT_CAUGHT] 把 after 改成 {MUTANT_VALUE} 竟没让判据红 ⇒ 门无牙")
        finally:
            os.unlink(tmp.name)

    def test_C_artifact_is_tracked_and_clean(self):
        """tracked：源文件必须在 git 跟踪内、且工作树副本 == HEAD blob（否则是临时目录里的口头数）。"""
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        ls = subprocess.run(["git", "ls-files", "--error-unmatch", ARTIFACT_REL],
                            cwd=str(ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=env)
        self.assertEqual(ls.returncode, 0,
                         f"[B_NOT_TRACKED] {ARTIFACT_REL} 不在 git 跟踪内 ⇒ (b) 参照数无仓内源头")
        head = subprocess.run(["git", "rev-parse", f"HEAD:{ARTIFACT_REL}"],
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
        cur = subprocess.run(["git", "hash-object", str(ARTIFACT)],
                             cwd=str(ROOT), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", env=env)
        self.assertEqual(head.stdout.strip(), cur.stdout.strip(),
                         f"[B_WORKTREE_DRIFT] 盘上副本({cur.stdout.strip()})≠HEAD blob"
                         f"({head.stdout.strip()}) —— 冻结证人文件被改过")


if __name__ == "__main__":
    unittest.main(verbosity=2)
