# -*- coding: utf-8 -*-
"""改写映射表的判据：配对、树闸门、残文扫描、恒等式、确定性。

为什么必须用临时仓做正例：这三条判据在**当前仓里全都处于"没抓到东西"的状态**
（problems=0、pending 只有一条已知欠账），只跑真仓等于只测了"绿"这一面。
所以每条都在 `%TEMP%` 里造一个真会触发它的仓：改message又改了树的（闸门必须红）、
message 带 `MSG;` 残文的（扫描必须数到它）。
确定性那条不是装饰：本生成器第一版只按提交日期排序，同秒的对象跟着 set 迭代序走，
而 set 序受 PYTHONHASHSEED 影响 —— 于是刚 `--write` 完的下一毫秒 `--verify` 就报"表被手改过"。
"""
from __future__ import annotations

import hashlib
import io
import re
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console import _rewrites as RW        # noqa: E402

ENV = dict(os.environ,
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e",
           GIT_AUTHOR_DATE="2026-01-01T00:00:00 +0800",
           GIT_COMMITTER_DATE="2026-01-01T00:00:00 +0800")


def _g(cwd, *args):
    pr = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, env=ENV)
    if pr.returncode:
        raise AssertionError("git %s 失败：%s" % (" ".join(args), pr.stderr.decode("utf-8", "replace")))
    return pr.stdout.decode("utf-8", "replace").strip()


def make_repo(case):
    """造一个小仓：case=message_only_rewrite | tree_changed_rewrite | residue。"""
    d = tempfile.mkdtemp(prefix="rw-test-")
    _g(d, "init", "-q", "-b", "main")
    io.open(os.path.join(d, "a.txt"), "w").write("1\n")
    _g(d, "add", "a.txt")
    _g(d, "commit", "-q", "-m", "初始")
    io.open(os.path.join(d, "a.txt"), "w").write("2\n")
    _g(d, "commit", "-qam", "改一点东西")
    io.open(os.path.join(d, "b.txt"), "w").write("x\n")
    _g(d, "add", "b.txt")
    _g(d, "commit", "-qm", "再加一个文件")     # tip = 要"改写"的那条
    tip = _g(d, "rev-parse", "HEAD")
    tree = _g(d, "rev-parse", "%s^{tree}" % tip)
    parent = _g(d, "rev-parse", "%s^" % tip)
    author = _g(d, "log", "-1", "--format=%an <%ae> %at %ad", tip)
    msg = "再加一个文件\n\n正文一行。\nMSG; git status --porcelain" if case == "residue" \
        else "再加一个文件\n\n正文一行（改写后）。"
    f = os.path.join(d, "m.txt")
    io.open(f, "w", encoding="utf-8").write(msg + "\n")
    if case == "tree_changed_rewrite":
        io.open(os.path.join(d, "b.txt"), "w").write("tampered\n")
        _g(d, "add", "b.txt")
        staged = _g(d, "write-tree")               # 故意用一棵不同的树去配同标题
        new_tree = staged
    else:
        new_tree = tree
    new = _g(d, "commit-tree", new_tree, "-p", parent, "-F", f)
    _g(d, "update-ref", "refs/heads/main", new, tip)
    _g(d, "update-ref", "refs/remotes/origin/master", _g(d, "rev-parse", "%s^" % new))
    # 不额外写 reflog：`update-ref` 对 refs/heads/* 本来就会留一条记录，
    # 生成器靠"旧 sha 是否当过分支头"区分 已改写 / 从未上头（dry-run）。
    return d, tip, new


class RewriteMapTests(unittest.TestCase):

    def test_live_repo_table_is_self_consistent(self):
        """真仓这一面：恒等式成立、问题数为 0、每个配对两端树相同。"""
        text, c = RW.report(ROOT)
        self.assertEqual(c["problems"], 0, "现况有问题条目：%s" % text.split("## 问题")[-1][:300])
        self.assertTrue(c["identity_ok"],
                        "分桶恒等式不成立（配对 %d + 悬空 %d vs 不可达 %d）"
                        % (c["rewritten"], c["dangling"], c["unreachable"]))
        self.assertGreaterEqual(c["rewritten"], 4,
                                "配对数掉到 %d：subject+tree+author 的配法或改写历史变了"
                                % c["rewritten"])
        self.assertIn("| 恒等式（配对 + 悬空 = 不可达） | 成立 |", text)

    def test_artifact_has_no_self_referential_counts(self):
        """产物里不许有"每一笔提交都会变"的绝对量 —— 否则承载它的那笔提交自己就把表弄过期。

        这不是理论：第一版印了 `对象库 commit 总数` 与 `从 HEAD 可达`，
        我提交完再跑一次 --write，两个数各自 +1，`--verify` 立刻红 ——
        一份永远"刚交付就过期"的产物，等于给下一个人留了个假故障。
        """
        text, _c = RW.report(ROOT)
        for banned in ("对象库里的 commit 总数", "从 HEAD 可达"):
            self.assertNotIn(banned, text,
                             "产物里出现了每笔提交都会变的量 %r；它只能出现在运行时读数行上"
                             % banned)
        # 提一句字段名是可以的（`cost_ms` 出现在说明里），把某个时刻的值烤进产物不行
        self.assertNotIn("cost_ms=", text, "产物里烤进了某一时刻的门成本值")
        # 反过来：不可达数、配对数、欠账数必须真的在（否则删过头，表就没内容可核了）
        for need in ("不可达（旧指针 + 无关悬空对象）", "改写配对出来的旧指针",
                     "仍含 `^MSG;` 的条数"):
            self.assertIn(need, text, "产物少了这一项：%s" % need)

    def test_table_is_deterministic_across_hash_seeds(self):
        """同一份仓、不同 PYTHONHASHSEED，必须产出逐字节相同的表。"""
        code = ("import sys, hashlib; sys.path.insert(0, %r);"
                "from console import _rewrites as RW;"
                "print(hashlib.sha256(RW.report()[0].encode('utf-8')).hexdigest())" % str(ROOT))
        digests = set()
        for seed in ("0", "1", "777", "424242"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            pr = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                                cwd=str(ROOT), capture_output=True, env=env)
            self.assertEqual(pr.returncode, 0, pr.stderr.decode("utf-8", "replace")[-200:])
            digests.add(pr.stdout.decode("utf-8", "replace").strip())
        self.assertEqual(len(digests), 1,
                         "同一份仓生成出 %d 种不同的表 —— 排序不是全序，--verify 会随机红"
                         % len(digests))

    def test_pending_residue_is_found_by_scanning_not_by_confession(self):
        """正例：造一条 message 里带 `MSG;` 的提交，扫描必须数到它。

        没有这条正例，"还欠几条"就只是一个我自己填的数字 —— 我可以永远说 0。
        """
        d, tip, new = make_repo("residue")
        text, c = RW.report(Path(d))
        self.assertEqual(c["pending"], 1,
                         "种了一条残文却没数到（pending=%d）：扫描形状变了\n%s"
                         % (c["pending"], text[text.find("## 还欠"):][:200]))
        self.assertIn(new[:7], text, "欠账表里没列出那条坏提交的活对端")
        self.assertIn("MSG;", text.split("## 还欠")[1], "欠账那节没带上残文本身")

    def test_tree_gate_catches_a_rewrite_that_changed_content(self):
        """正例：改写时顺手改了树 —— 闸门必须红，不能只当作"换了个指针"。"""
        d, tip, new = make_repo("tree_changed_rewrite")
        text, c = RW.report(Path(d))
        self.assertGreaterEqual(c["problems"], 1,
                                "树被改了却没报问题：这道闸门不成立\n%s" % text[-400:])
        self.assertTrue(any("树不相等" in p or "无法唯一" in p
                            for p in [l for l in text.split("\n") if l.startswith("- ")]),
                        "问题条目没指明是树不相等：%s" % text[text.find("## 问题"):][:300])
        rc = RW.main(["--verify"], Path(d))
        self.assertEqual(rc, 1, "有问题却退出码 0 —— 这道门不会拦")

    def test_stale_and_missing_table_go_red(self):
        """判别式：盘上的表与现算不一致、或表不存在，都要红（否则它是手抄件）。"""
        d, tip, new = make_repo("message_only")
        RW.main(["--write"], Path(d))
        out = Path(d) / RW.OUT_REL
        self.assertTrue(out.is_file(), "--write 没落盘")
        self.assertEqual(RW.main(["--verify"], Path(d)), 0, "刚生成完就验不过（这一条同时兜确定性）")
        original = out.read_bytes()
        try:
            out.write_bytes(original.replace(b"## ", b"## X", 1))
            self.assertEqual(RW.main(["--verify"], Path(d)), 1, "表被改了一个字节却不红")
        finally:
            out.write_bytes(original)
        self.assertEqual(RW.main(["--verify"], Path(d)), 0, "还原后仍不红=还原失败")
        out.unlink()
        self.assertEqual(RW.main(["--verify"], Path(d)), 1, "表没了却不红")


    def test_docs_cite_only_resolvable_or_listed_shas(self):
        """活文档里每个 sha：要么从 HEAD 可达，要么出现在自动生成的映射表里。

        这条是给"台账只记 sha"那个坑兜底的：改写让 `007be71` 这类"当时的现 sha"再次变成
        不可达时，只要映射表（自动生成）里有它，引用就不算断；等 `git gc` 把对象回收掉，
        这条就会红 —— 那正是"该改用标题复算式"的时刻，而不是等到有人 grep 不到才发现。
        """
        sha_re = re.compile(r"\b[0-9a-f]{7,40}\b")
        full = set(subprocess.run(
            ["git", "rev-list", "--all", "--reflog"], cwd=str(ROOT), capture_output=True,
            text=True).stdout.split())
        # 文档里引用的是 7 字短号，可达集里是 40 字长号 —— 直接 `tok in full`
        # 会让每个短号都"看着不可达"（第一版就是这样误报 77 处）。按前缀比，
        # 并断言这批对象里没有 7 字前缀相撞，否则这个近似本身不成立。
        pref = set()
        for x in full:
            pref.add(x[:7])
        assert len(pref) == len(full), "7 字前缀有相撞，按前缀判可达不成立"
        reachable = full | pref
        table = (ROOT / RW.OUT_REL).read_text(encoding="utf-8")
        listed = set(sha_re.findall(table))
        checked = bad = 0
        where = []
        for rel in ["README.md", "CHANGELOG.md"] + [
                p.relative_to(ROOT).as_posix() for p in (ROOT / "docs").glob("*.md")]:
            for ln, line in enumerate(io.open(ROOT / rel, encoding="utf-8",
                                              errors="replace").read().split("\n"), 1):
                for tok in sha_re.findall(line):
                    # 只问像 sha 的、且在 git 里确实存在的（排除版本号之类的假命中）
                    pr = subprocess.run(["git", "cat-file", "-t", tok], cwd=str(ROOT),
                                        capture_output=True, text=True)
                    if pr.returncode or "commit" not in pr.stdout:
                        continue
                    checked += 1
                    if tok not in reachable and tok not in {s[:len(tok)] for s in listed}:
                        bad += 1
                        where.append("%s:%d %s" % (rel, ln, tok))
        print("[DOC_SHA_CENSUS] commit_sha_引用=%d 不可达且未列入映射表=%d"
              " | 活文档里引用的 sha %d 处，其中 %d 处既不可达也不在映射表里"
              % (checked, bad, checked, bad))
        self.assertGreaterEqual(checked, 20,
                                "只核到 %d 个 sha 引用：扫描范围塌了（README/CHANGELOG/docs 都应在）"
                                % checked)
        self.assertEqual(bad, 0, "这些 sha 在活文档里被引用，却既不可达也没进映射表：\n  %s"
                         % "\n  ".join(where[:10]))


if __name__ == "__main__":
    unittest.main()
