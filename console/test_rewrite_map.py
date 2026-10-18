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

# GitHub 不能复制原工作区的 reflog、stash、已改写旧对象。portable 在
# 浅/完整克隆上都必须实际执行，绝不以 skip 代替；local 必须显式授权。
MODE = os.environ.get("SWARM_REWRITE_TEST_MODE", "portable").lower()
if MODE not in {"portable", "local"}:
    raise RuntimeError("SWARM_REWRITE_TEST_MODE 只接受 portable 或 local，实际：" + MODE)


def archived_text():
    return (ROOT / RW.OUT_REL).read_text(encoding="utf-8")


ENV = dict(os.environ,
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e",
           GIT_AUTHOR_DATE="2026-01-01T00:00:00 +0800",
           GIT_COMMITTER_DATE="2026-01-01T00:00:00 +0800")


def _w(path, text):
    """写文件并**确实关掉句柄**：`io.open(...).write(...)` 会漏，
    而 `warnings="default"` 一开就会以 `ResourceWarning` 冒出来（真套件 A/B 实测 92 条）。"""
    Path(path).write_text(text, encoding="utf-8")


def _g(cwd, *args):
    pr = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, env=ENV)
    if pr.returncode:
        raise AssertionError("git %s 失败：%s" % (" ".join(args), pr.stderr.decode("utf-8", "replace")))
    return pr.stdout.decode("utf-8", "replace").strip()


def make_repo(case):
    """造一个小仓：case=message_only_rewrite | tree_changed_rewrite | residue。"""
    d = tempfile.mkdtemp(prefix="rw-test-")
    _g(d, "init", "-q", "-b", "main")
    _w(os.path.join(d, "a.txt"), "1\n")
    _g(d, "add", "a.txt")
    _g(d, "commit", "-q", "-m", "初始")
    _w(os.path.join(d, "a.txt"), "2\n")
    _g(d, "commit", "-qam", "改一点东西")
    _w(os.path.join(d, "b.txt"), "x\n")
    _g(d, "add", "b.txt")
    _g(d, "commit", "-qm", "再加一个文件")     # tip = 要"改写"的那条
    tip = _g(d, "rev-parse", "HEAD")
    tree = _g(d, "rev-parse", "%s^{tree}" % tip)
    parent = _g(d, "rev-parse", "%s^" % tip)
    author = _g(d, "log", "-1", "--format=%an <%ae> %at %ad", tip)
    msg = "再加一个文件\n\n正文一行。\nMSG; git status --porcelain" if case == "residue" \
        else "再加一个文件\n\n正文一行（改写后）。"
    f = os.path.join(d, "m.txt")
    _w(f, msg + "\n")
    if case == "tree_changed_rewrite":
        _w(os.path.join(d, "b.txt"), "tampered\n")
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
        """portable: 可移植归档硬门；local: 原对象库和 reflog 的严格门。"""
        print("[REWRITE_TEST_MODE] %s" % MODE, flush=True)
        if MODE == "portable":
            self.assertEqual(RW.verify_portable(ROOT), 0,
                             "可访问提交/归档不一致；未下载的历史只允许具名 NOT VERIFIED")
            return
        # 显式 local：沿用原开发仓库的对象库全量检查；不自动降级为绿。
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
        text = archived_text() if MODE == "portable" else RW.report(ROOT)[0]
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
        # 真仓旧对象集在两台机器上不相同；在新造的同一临时仓内
        # 比较四种 PYTHONHASHSEED，才能测到生成器确定性而不依赖原 reflog。
        fixture, _old, _new = make_repo("message_only")
        code = ("import sys, hashlib; from pathlib import Path;"
                "sys.path.insert(0, %r);"
                "from console import _rewrites as RW;"
                "print(hashlib.sha256(RW.report(Path(%r))[0].encode('utf-8')).hexdigest())"
                % (str(ROOT), fixture))
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

    def test_amended_tip_is_named_not_swallowed(self):
        """amend 只改消息留下的旧 tip：必须被具名认出来，且**非 tip 位置不许被它放行**。

        为什么值得一条用例：本轮我自己 amend 了一次（改提交信息里的失实措辞），
        映射表当场把那条旧 tip 报成"未归类"、`--verify` 退出码 1。修法不能是"见到
        tree 相同就放行" —— 那等于给任意历史重写开一个口袋；所以判据锁三条：
        同 tree+parent+作者时间戳、subject 不同、活对端仍是分支头、且旧 sha 在 reflog 里当过头。
        """
        d, tip, new = make_repo("message_only")
        text, c = RW.report(Path(d))
        self.assertEqual(c["problems"], 0, "干净的一次改写却报了问题：%s" % text[-400:])
        # 同 subject 的改写走的是"配对"那条路（本来就认得）；要测新加的 amend 分类，
        # 必须造一个**标题也不同**的旧 tip —— 那才是本轮真撞到的形状。
        f = os.path.join(d, "m2.txt")
        _w(f, "再加一个文件（换了措辞）\n\n正文一行。\n")
        tip2 = new
        tree2 = _g(d, "rev-parse", "%s^{tree}" % tip2)
        parent2 = _g(d, "rev-parse", "%s^" % tip2)
        a_name, a_mail, a_ts = _g(d, "log", "-1", "--format=%an%x00%ae%x00%at", tip2).split("\x00")
        # `commit-tree` 没有 --author-time/--date 之外还能塞环境变量：用 GIT_AUTHOR_* 三个量
        # 把作者与时间戳原样带过去，只换 subject —— 这才是 amend 的形状。
        env2 = dict(ENV)
        env2.update({"GIT_AUTHOR_NAME": a_name, "GIT_AUTHOR_EMAIL": a_mail,
                     "GIT_AUTHOR_DATE": "@%s +0000" % a_ts})
        cmd = ["git", "commit-tree", tree2, "-p", parent2, "-F", f]
        pr = subprocess.run(cmd, cwd=d, capture_output=True, env=env2)
        if pr.returncode:
            raise AssertionError("git commit-tree 失败：%s" % pr.stderr.decode("utf-8", "replace"))
        new2 = pr.stdout.decode().strip()
        _g(d, "update-ref", "refs/heads/main", new2, tip2)
        text, c = RW.report(Path(d))
        self.assertIn("amend 掉的旧 tip", text,
                      "换了措辞的 amend 留下的旧 tip 没被具名归类：%s" % text[-400:])
        self.assertEqual(c["problems"], 0, "认出来了却仍报问题：%s" % text[-400:])
        self.assertEqual(RW.classify_amended_tip(Path(d), [tip2], {new2}), {tip2: new2},
                         "三条判据都成立却没认出来")
        # 反例①（这条同时兜住我犯过的方向错误）：判据不能写成"活对端现在仍是 tip"，
        # 否则仓往前走几步之后，这条门会在**健康仓**上自己变红 —— 本轮真撞到过一次。
        _g(d, "commit", "-q", "--allow-empty", "-m", "后一笔")
        moved_head = _g(d, "rev-parse", "HEAD")
        self.assertEqual(RW.classify_amended_tip(Path(d), [tip2], {new2}), {tip2: new2},
                         "被 amend 的那条已不是当前 tip 就不认了？判据写歪了")
        # 反例②：旧 sha 从没当过分支头 ⇒ 不许认（拿一个从未上头的对象试）
        other = _g(d, "commit-tree", _g(d, "rev-parse", "%s^{tree}" % moved_head),
                   "-p", _g(d, "rev-parse", "%s^" % moved_head), "-m", "从未上头的同类对象")
        self.assertNotIn(other, set(RW.classify_amended_tip(Path(d), [other], {moved_head})),
                         "reflog 里没有它却被认成 amend 产物")

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
        """portable 报告可证明/仅归档/未取得对象；local 保留原历史严格审计。"""
        sha_re = re.compile(r"\b[0-9a-f]{7,40}\b")
        reachable_rc, reach_data = RW._git(ROOT, "rev-list", "HEAD")
        self.assertEqual(reachable_rc, 0, "git rev-list HEAD 执行失败")
        reachable = set(reach_data.split())
        self.assertGreater(len(reachable), 0, "当前克隆没有任何可达提交")
        snapshot = archived_text()
        rows, problems, _ = RW.audit_portable_snapshot(snapshot)
        self.assertFalse(problems, "归档结构不符合可移植验证门：%s" % problems)
        archived_ids = {old for _, old, _, _, _ in rows}
        archived_ids.update(new for _, _, new, _, _ in rows)
        # 原表的“与改写无关的不可达对象”也必须纳入归档标识。
        area = snapshot.split("### 与改写无关的不可达对象", 1)[1].split(
            "## 还欠的残文", 1)[0]
        archived_ids.update(re.findall(r"^\| `([0-9a-f]{7,40})` \|", area, re.M))
        refs = []
        for rel in ["README.md", "CHANGELOG.md"] + [
                p.relative_to(ROOT).as_posix() for p in (ROOT / "docs").glob("*.md")]:
            content = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            refs.extend((rel, line_no, token)
                        for line_no, line in enumerate(content.splitlines(), 1)
                        for token in sha_re.findall(line))
        self.assertGreaterEqual(len(refs), 20, "文档扫描覆盖塌缩（不足 20 个 sha 形状）")

        def matches(token, values):
            return any(value.startswith(token) or token.startswith(value) for value in values)

        if MODE == "portable":
            visible = [(p, ln, v) for p, ln, v in refs if matches(v, reachable)]
            archival = [(p, ln, v) for p, ln, v in refs
                        if not matches(v, reachable) and matches(v, archived_ids)]
            unknown = [(p, ln, v) for p, ln, v in refs
                       if not matches(v, reachable) and not matches(v, archived_ids)]
            self.assertGreater(len(visible) + len(archival), 0,
                               "既没有可达引用也没有归档引用，SHA 检查在空转")
            print("[DOC_SHA_PORTABLE] scanned=%d reachable_refs=%d archived_only=%d "
                  "unresolved_not_verified=%d mode=%s sample=%s" %
                  (len(refs), len(visible), len(archival), len(unknown),
                   MODE, unknown[:3]), flush=True)
            # 不可访问的任意 sha 不能冒充 commit，尤其是在浅克隆中。
            # 只有确定可达/明确归档的才称作已识别，其余只称 NOT VERIFIED。
            return

        # local 严格模式：原工作区所有 commit 对象和 reflog 实际都能枚举。
        all_refs = set(RW.git(ROOT, "rev-list", "--all", "--reflog").split())
        full = all_refs | {x[:7] for x in all_refs}
        commits = set(RW._obj_lines(ROOT, "commit"))
        commit_pref = {x[:7] for x in commits}
        self.assertEqual(len(commit_pref), len(commits), "旧对象短 SHA 冲突")
        self.assertEqual(len({x[:7] for x in all_refs}), len(all_refs),
                         "reflog 可达对象短 SHA 冲突")
        listed = set(sha_re.findall(snapshot))
        verified = 0
        missing = []
        for rel, ln, token in refs:
            if token not in commits and token not in commit_pref:
                continue
            verified += 1
            if token not in full and not matches(token, listed):
                missing.append("%s:%d %s" % (rel, ln, token))
        print("[DOC_SHA_LOCAL] commit_refs=%d missing=%d" %
              (verified, len(missing)), flush=True)
        self.assertGreaterEqual(verified, 20,
                                "原始工作区 commit 引用覆盖下降；禁止自动降级为 portable")
        self.assertFalse(missing, "对象不可达且未列入归档：\n  " + "\n  ".join(missing[:10]))

    def test_batch_read_matches_per_object_read(self):
        """批读通道必须与逐条 `git show -s --format=` 给出同样的字段，含三类边界标题。

        为什么值得单独一条：性能优化把取数搬进了 `git log --stdin` 一次读全量。
        上一版这里是我自己解析 commit 原文 + `.strip()` 取标题 —— 变异"去掉 strip"当场全绿，
        不是判据瞎，而是本仓没有能区分它的标题。**造数据之后才看得见**：
        git 的 `%s` 保留前导空格、去掉尾随空格，而我那版把两头都吃了。

        本轮记三条（都可复算）：
        - 变异 M1（把 `.strip()` 加回批读的标题字段）⇒ 红，`不一致=1`。
          同一个变异在加边界标题夹具之前是**绿**的，这才是夹具在承重。
        - 变异 M3（提前建批表，让边界对象落到单条兜底）⇒ 红，`assertIn` 点名标题。
        - 消融（删掉 `_BATCH.pop`）⇒ 绿，所以那句兜底已删，只留断言。
        """
        def read(root, args):
            """按字节读再用 utf-8 解 —— 这条不是风格选择：`text=True` 在这台机上用
            GBK 解 git 的 UTF-8 输出，reader 线程抛 UnicodeDecodeError 后
            subprocess 把 stdout 变成 **None**（异常只打到 stderr，rc 仍是 0）。
            第一版就是这样：样本里换一批 sha 就从绿变崩，判据本身跟着数据漂。"""
            pr = subprocess.run(["git"] + args, cwd=str(root), capture_output=True)
            assert pr.returncode == 0, "git %s 失败：%s" % (" ".join(args), pr.stderr[:120])
            return pr.stdout.decode("utf-8", "replace").rstrip("\r\n").split("\x00")

        def both(sha):
            # 批读必须真的供货：落在 `fields()` 的单条兜底分支上就等于没核批读通道。
            assert sha in RW._commit_batch(ROOT), \
                "%s 没进批读表，fields() 会走单条兜底 —— 这条用例就没测到批读" % sha[:7]
            batched = RW.fields(ROOT, sha)
            single = read(ROOT, ["show", "-s", "--format=" + RW._FIELDS_FMT, sha])
            return batched, single
        reachable = set(RW.git(ROOT, "rev-list", "HEAD").split())
        self.assertTrue(reachable, "HEAD 不可达，批量读校验无分母")
        if MODE == "local":
            shas = RW._obj_lines(ROOT, "commit")
            sample = [s for s in shas if s not in reachable] + \
                     sorted(s for s in shas if s in reachable)[:20]
        else:
            # 浅克隆可能只有 HEAD。永不以本地不可达对象数量为门槛。
            sample = sorted(reachable)[:20]
        mism = ["%s\n   批读 %r\n   逐条 %r" % (s[:7], *both(s))
                for s in sample if both(s)[0] != both(s)[1]]
        # 边界标题：前导空格、尾随空格、首个非空行之前有空行。
        # 三个 commit 先全部造完、再一次性读批表，然后用 assertIn 钉住"这几个对象
        # 确实在批表里"：批读是按仓缓存的，边造边读时后两个会静默落到单条兜底上，
        # 那"边界标题测的是批读"就变成一句空话（变异 M3：提前建表 ⇒ 三条全红）。
        # 曾在这里加过 `RW._BATCH.pop(...)` 兜这个坑，消融后确认不需要 —— 仓目录来自
        # mkdtemp、每次都是新键，缓存不可能预先有值 —— 所以只留下断言，不留兜底。
        d, _tip, _new = make_repo("message_only")
        edge = ["   前导空格的标题", "尾随空格的标题   ", "普通标题"]
        made = []
        for i, msg in enumerate(edge):
            p = os.path.join(d, "edge%d.txt" % i)
            _w(p, "x\n")
            _g(d, "add", p)
            _g(d, "commit", "-q", "-m", ("\n\n" + msg) if i == 2 else msg)
            made.append((msg, _g(d, "rev-parse", "HEAD")))
        tb = RW._commit_batch(Path(d))
        for msg, sha in made:
            self.assertIn(sha, tb, "边界标题 %r 的对象没进批读表" % msg)
            b, s = list(tb[sha]), read(d, ["show", "-s", "--format=" + RW._FIELDS_FMT, sha])
            if b != s:
                mism.append("边界标题 %r：批读 %r vs 逐条 %r" % (msg, b[4], s[4]))
        # 逐条读自己也得复核一遍口径：git 的 %s 保留前导空格、去掉尾随空格。
        # 断言这条，是为了"批读==逐条"之外再钉住"两边都不是我手工切的标题"。
        self.assertEqual(read(d, ["show", "-s", "--format=%s", made[0][1]])[0],
                         "   前导空格的标题", "git 不再保留前导空格：这条用例的前提变了")
        self.assertEqual(read(d, ["show", "-s", "--format=%s", made[1][1]])[0],
                         "尾随空格的标题", "git 不再去掉尾随空格：这条用例的前提变了")
        print("[BATCH_EQUIV] mode=%s real_commits=%d fixture_edges=3 mismatch=%d "
              "local_only_unreachable=%d" %
              (MODE, len(sample), len(mism),
               len([x for x in sample if x not in reachable])), flush=True)
        self.assertGreaterEqual(len(sample), 40 if MODE == "local" else 1,
                                "当前模式可访问的 commit 样本数不足：%d" % len(sample))
        self.assertEqual(mism, [], "批读与逐条读不等价：\n  " + "\n  ".join(mism[:4]))


if __name__ == "__main__":
    unittest.main()
