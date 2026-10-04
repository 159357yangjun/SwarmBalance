# -*- coding: utf-8 -*-
r"""提交改写映射表：整张表从对象库里算出来，一个数都不手填。

为什么要有这个生成器（连着三次同一族）：这张表第一版是我手写的，于是
"实测 82 vs 印 83"、"现 sha 填成 dry-run 对象"、"7 个指针其实是 11 个" 三次都错在
**抄**。抄下来的派生值会随仓库自己动，而下一个人只能重新推断一遍。

全部字段都可复算，所以全部现算：
- 谁是"活的对端"：按 subject + tree + author 行三样同时相等去配（不靠我记的映射）；
- 谁是"从未上过头"（dry-run 或被替换的中间父）：看它有没有出现在 `refs/heads/main` 的 reflog 里；
- 还欠几条残文：直接扫 HEAD 可达的每条 message 是否含 `^MSG;`，不等我承认；
- 每条欠账要重落几个指针：`rev-list --count <坏>..HEAD + 1`（这个数上一轮记成 9，
  现在自己变成 11 —— 因为我之后又提交了，任何记下来的值都必然过期）。

安全闸门（对**我自己过去做过的事**，不是提醒）：
- 每一条被配对出来的旧对象都必须**不是** `origin/master` 的祖先；
  只要有一条是，就说明改写动过已推出去的历史 —— 直接判失败。
- 每个坏 sha 与活 sha 的 `git diff` 必须为空（树未变）。

用法：
    python console/_citations.py --rewrite-report            # 打印
    python console/_citations.py --rewrite-report --write    # 生成 docs/提交改写映射表.md
    python console/_citations.py --rewrite-report --verify   # 与盘上不一致退出码 1
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_REL = "docs/提交改写映射表.md"
RESIDUE = re.compile(r"^MSG;", re.M)          # heredoc 收尾被吞进 message 的形状
PUSHED = "origin/master"
BRANCH = "refs/heads/main"


def _git(root, *args):
    pr = subprocess.run(["git"] + list(args), cwd=str(root), capture_output=True)
    return pr.returncode, pr.stdout.decode("utf-8", "replace")


def git(root, *args):
    rc, out = _git(root, *args)
    return out.strip() if rc == 0 else ""


def _obj_lines(root, typ):
    """对象库里该类型的所有 sha（`--batch-check` 一次拿全，别一个 cat-file 一次）。"""
    rc, out = _git(root, "cat-file", "--batch-all-objects", "--batch-check=%(objecttype) %(objectname)")
    if rc:
        raise SystemExit("git cat-file --batch-all-objects 失败：改写映射表无法生成")
    return [ln.split()[1] for ln in out.splitlines() if ln.startswith(typ + " ")]


_BATCH = {}
_FIELDS_FMT = "%T%x00%P%x00%an <%ae>%x00%at%x00%s"


def _commit_batch(root):
    """一次 `git log --no-walk --format=… --stdin` 读完所有 commit 的头部字段。

    为什么不是自己解析 `cat-file` 出来的原始对象：`%s` 的口径不是"第一行"——
    实测三条边界（标题行前置空行 → git 取第一个非空行；标题**前导空格保留**、尾随空格去掉；
    普通标题一致），我自己那版 `.split(换行)[0].strip()` 会把前导空格也吃掉，
    于是配对的键就和 git 给的不一样了。让 git 自己格式化，等价性是构造出来的，
    不靠我比对样本碰运气（`console/test_rewrite_map.py` 的 `test_batch_read_matches_per_object_read`
    逐字段比对批读与单条 `git show`，并用三类边界标题钉住 `%s` 的口径）。
    进程数与对象数无关：**按 commit 取字段**这件事只有一次 `git log --stdin`（按仓缓存），
    之后 `fields()` 全查内存；表里其它调用（`rev-list` / `reflog` / 逐对 `git diff`）与本句无关。
    """
    key = str(root)
    if key in _BATCH:
        return _BATCH[key]
    shas = _obj_lines(root, "commit")
    info = {}
    if shas:
        # 记录之间用 %x01 分隔：字段内可能出现制表/空格，但绝不会出现 \x01。
        pr = subprocess.run(
            ["git", "log", "--no-walk", "--format=%x01%H%x00" + _FIELDS_FMT, "--stdin"],
            cwd=str(root), input=("\n".join(shas) + "\n").encode("utf-8"),
            capture_output=True)
        if pr.returncode:
            raise SystemExit("git log --no-walk --stdin 失败：%s"
                             % pr.stderr.decode("utf-8", "replace")[:200])
        for rec in pr.stdout.decode("utf-8", "replace").split("\x01"):
            rec = rec.strip("\r\n")
            if not rec.strip():
                continue
            parts = rec.split("\x00")
            if len(parts) != 6:
                raise SystemExit("git log 返回的记录形状不对（%d 段）：%r"
                                 % (len(parts), rec[:80]))
            info[parts[0]] = parts[1:]
        if len(info) != len(set(shas)):
            raise SystemExit("批读只取到 %d / %d 个 commit，宁可停下也不要用半份数据出表"
                             % (len(info), len(set(shas))))
    _BATCH[key] = info
    return info


def fields(root, sha):
    """commit 的 (tree, parents, `作者 <邮箱>`, 时间戳, 标题)。

    批读取不到时退回单条 `git show -s`（调用方可能传缩写 sha 或批读窗口外的 sha）。
    """
    got = _commit_batch(root).get(sha)
    if got is None:
        return git(root, "show", "-s", "--format=" + _FIELDS_FMT, sha).split("\x00")
    return list(got)


NOTES_REL = "docs/不可达对象溯源注.md"


def _load_dangling_notes(root):
    """读 `docs/不可达对象溯源注.md`，返回 {短 sha: 说明}。

    为什么单独一个文件：映射表本体是 git 现算、且被逐字节比对 ⇒ 任何手改都会在下次
    `--write` 时消失（本轮就真撞上过一次：给 stash 对象补的说明被重生覆盖）。
    格式：每行 `- `<sha>`｜<说明>`；sha 取前 7~40 位均可，按前缀匹配。
    """
    p = Path(root) / NOTES_REL
    if not p.is_file():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip().lstrip("-").strip()
        if "`" not in s or "｜" not in s and "|" not in s:
            continue
        sha = s.split("`")[1].strip()
        rest = s.split("｜", 1)[-1] if "｜" in s else s.split("|", 1)[-1]
        note = rest.strip()
        if sha and note and not note.startswith("说明"):
            out[sha[:7]] = note.replace("\n", " ")
    return out


def classify_dangling(subject, parents):
    """给"配不上对的不可达提交"一个名字，而不是把它当失败。

    不可达 != 改写产物。本仓第一次跑这道判据时，不可达对象里就混着**不是**改写造出来的
    那一类：`git stash` 留下的（`On <branch>: …` / `index on <branch>: …` 是它的固定格式）
    和孤儿初始提交。**一个都不会红** —— 但要被点到名字：
    把解释不了的悬空对象当"已说明"放过去，就等于给下一次改写留了个隐身位。
    各多少不抄在这里（它们随仓动）：`--rewrite-report` 把每个对象连归类印成表，
    恒等式 `pairs + dangling == unreachable` 写在同一份输出里，当场可核。

    **第三种形状是 amend 自己造的，本轮真撞上过一次**：把 tip 的消息改个措辞再 amend，
    旧 tip 变成不可达、而活对端**标题不同**（消息就是被改的东西），于是按 subject 配不上对。
    它不是改写历史出错，但也不能被静默放行 —— 所以给它一个具名类别：**只允许 amend 在 tip 上**
    （活分支的最后一个提交）。非 tip 位置出现同形状的悬空对象，说明被动过的不是消息而是顺序或内容，
    那种必须继续报"未归类"并让 `--verify` 红。
    """
    if not parents:
        return "孤儿根提交（另一段历史，无父）"
    if subject.startswith("index on ") or subject.startswith("On ") \
            or subject.startswith("WIP on "):
        # WIP on <branch>: 是 stash 为"已跟踪改动"造的那个提交的固定标题（本轮我自己
        # `git stash push -u` 之后 pop 完，stash ref 已空但这个对象仍活在对象库里）。
        # 它是三 parent 的机械产物，与"改写历史"无关；此前只认 On/index on ⇒ 漏认。
        return "git stash 留下的对象（stash ref 已清，对象未回收）"
    return ""


def classify_amended_tip(root, unreachable, live):
    """把"amend 掉出去的旧 tip"从'未归类'里认出来，返回 {旧 sha: 活对端 sha}。

    判据三条同时成立才算：① 它与某个活提交**同 tree、同 parent、同作者时间戳**，只有 subject
    不同（这正是"只改消息"的形状）；② 那个活对端**在 reflog 里当过分支头** —— amend 只能发生在
    tip 上，从未上头的同形状对象不算；③ 旧 sha 同样在 reflog 里当过头。少任何一条都不认 ——
    否则"未归类"这道门就有了一个能装下任意历史重写的口袋。

    ②说的是"**曾经**是 tip"而不是"**现在**仍是 tip"：仓往前走几步之后，被 amend 的那条早就不在
    tip 上了；用"现在是 tip"当条件，这道门会在健康仓上自己变红（本轮实测撞到过一次）。
    """
    out = {}
    if not live:
        return out
    # 不只读主分支的 reflog：改写历史那几轮里被动过的分支未必是当前 BRANCH。
    was_tip = set(git(root, "reflog", "show", "--format=%H", BRANCH).split())
    for br in git(root, "for-each-ref", "--format=%(refname)", "refs/heads").split():
        was_tip.update(git(root, "reflog", "show", "--format=%H", br).split())
    if not was_tip:
        return out
    live_by_key = {}
    for l in sorted(live):
        tree, parents, author, ts, subj = fields(root, l)
        live_by_key.setdefault((tree, parents, author, ts), []).append(l)
    for u in unreachable:
        if u not in was_tip:
            continue
        tree, parents, author, ts, subj = fields(root, u)
        cands = [p for p in live_by_key.get((tree, parents, author, ts), [])
                 if p in was_tip and fields(root, p)[4] != subj]
        if len(cands) == 1:
            out[u] = cands[0]
    return out


def report(root=ROOT):
    """-> (markdown, 统计字典)。统计字典用来在退出码之前先把话说清。"""
    live = set(git(root, "rev-list", "HEAD").split())
    if not live:
        raise SystemExit("rev-list HEAD 为空：这不是一个可用的仓，映射表无法生成")
    allc = set(_obj_lines(root, "commit"))
    # 排序必须**全序**：只按提交日期排，遇到同秒的（孤儿根、同一轮造的多个对象）就会
    # 跟着 set 的迭代序走 —— 而 set 序受 PYTHONHASHSEED 影响，于是同一份仓两次生成的
    # 表文本不同，`--verify` 在刚 --write 完之后就会红。（这不是理论问题：第一次跑就是这样。）
    def _dkey(s):
        return (fields(root, s)[3], s)
    unreachable = sorted(allc - live, key=_dkey)
    tips = set(git(root, "reflog", "show", "--format=%H", BRANCH).split())
    # 活集合：优先用"未推的那一段"；`origin/master` 这个 ref 不在（换机器/新克隆）就退回
    # 整个 HEAD 可达集，并在表里说明 —— 这道门不许因为别人仓的状态而误红。
    # 但"只看范围为空"是不够的（本轮实测撞到两次）：只要往已推历史后面再提一笔，
    # `origin/master..HEAD` 就变成 1 条，而被 amend 的旧对象其活对端大多在**更早、已推送**的
    # 区间里 ⇒ 候选集再次缺对端，同一批误红复发。所以判据不能猜范围大小，只能看结果：
    # 先用未推段建候选，若仍有"配不上对且形状像改写"的不可达对象，就用 HEAD 全可达集重试。
    pushed_ok = git(root, "rev-parse", "--verify", "--quiet", PUSHED) != ""
    range_spec = ("%s..HEAD" % PUSHED) if pushed_ok else "HEAD"

    def _subjects(spec):
        d = {}
        for sha in git(root, "rev-list", spec).split():
            d.setdefault(fields(root, sha)[4], []).append(sha)
        return d

    live_subjects = _subjects(range_spec)
    if pushed_ok and range_spec != "HEAD":
        # 重试条件与主循环同源：任何一条"同 subject 找不到同 tree 的活对端"都说明候选集偏小。
        unreachable_probe = set(_obj_lines(root, "commit")) - set(git(root, "rev-list", "HEAD").split())
        need_wider = any(fields(root, u)[4] not in live_subjects or
                         not [l for l in live_subjects.get(fields(root, u)[4], [])
                              if fields(root, l)[0] == fields(root, u)[0]]
                         for u in sorted(unreachable_probe))
        if need_wider:
            wider = _subjects("HEAD")
            # 只扩不缩：宽集合里能配上对的才采用，避免把"确实无关的悬空"洗成配对。
            live_subjects = wider

    rows, problems, pushed_dirty, dangling = [], [], [], []
    # amend 造成的旧 tip 单独认一次（它按 subject 配不上对，但形状是"只改消息"）：
    # 判据见 classify_amended_tip —— 三条同时成立才算，否则仍走"未归类"并红。
    amended = classify_amended_tip(root, unreachable, live)
    for u in unreachable:
        tree, parents, author, ts, subj = fields(root, u)
        cands = [l for l in live_subjects.get(subj, []) if fields(root, l)[0] == tree
                 and fields(root, l)[2] == author and fields(root, l)[3] == ts]
        if not cands:
            # 根提交不参与"树不等"判定：它没有 parent，"改写前的同一位置"这个前提不存在。
            # 同一初始内容被反复重造会产生多个无 parent、同标题同作者同时刻而 tree 不同的根
            # （实测 0682ae0/77b4594 与活在 main+dev+master 上的 4d8ac93 就是这样撞在一起的），
            # 把它们叫"改写动了内容"是误红 —— 它们从来不是同一次改写的两端。归入悬空并说明。
            if not parents:
                dangling.append((u, "root-with-same-stamp（无 parent 的根提交，与活根同标题同时刻"
                                    "但树不同；不构成改写两端）", subj))
                continue
            # 放宽 tree 再找一次：找到就说明"标题/作者/时间都对，只有树不同" ——
            # 那正是"改写时顺手改了内容"的形状，必须点名为树不等，不能含糊成"配不上对"。
            loose = [l for l in live_subjects.get(subj, [])
                     if fields(root, l)[2] == author and fields(root, l)[3] == ts]
            if len(loose) == 1 and fields(root, loose[0])[0] != tree:
                problems.append("树不相等：%s 与活对端 %s 标题/作者/时间戳都相同，但 tree 不同"
                                "（%s vs %s）—— 改写只许动 message，不许动内容"
                                % (u[:7], loose[0][:7], tree[:7], fields(root, loose[0])[0][:7]))
                rows.append(("树不等", u, loose[0], subj, "在" if u in tips else "不在"))
                continue
            why = classify_dangling(subj, parents)
            if not why:
                peer = amended.get(u)
                if peer:
                    # amend 只改消息：旧 tip 与活 tip 同 tree、同 parent、同作者时间戳。
                    # 具名放行，但把两端 sha 印进表里 —— 静默放行才是这道门最坏的失效方式。
                    why = "amend 掉的旧 tip（消息改写，tree 未变；活对端 %s）" % peer[:7]
                    rows.append(("消息改写", u, peer, subj, "在" if u in tips else "不在"))
                else:
                    problems.append("不可达提交 %s（%r）配不上对，也归不进任何已知的悬空类别"
                                    % (u[:7], subj[:40]))
                    why = "未归类"
            dangling.append((u, why, subj))
            continue
        if len(cands) > 1:
            problems.append("subject %r 在活分支上有 %d 个同 tree 的对端，无法唯一定位"
                            % (subj[:40], len(cands)))
        live_sha = cands[0]
        rc, _ = _git(root, "diff", "--quiet", u, live_sha)
        if rc:
            problems.append("%s 与其活对端 %s 树不相等 —— 改写动了内容，不只是 message" %
                            (u[:7], live_sha[:7]))
        _rc, _out = _git(root, "merge-base", "--is-ancestor", u, PUSHED)
        if _rc == 0:
            pushed_dirty.append(u)
        rows.append(("已改写" if u in tips else "从未上头", u, live_sha,
                     subj, "在" if u in tips else "不在"))
    for u in pushed_dirty:
        problems.append("不可达提交 %s 已在 %s 里 —— 改写动过已推出的历史" % (u[:7], PUSHED))

    # 还欠几条残文：扫活分支自己，不等我承认。
    # 一条 `git log` 拿全部 message（原来每条起一个子进程，111 个 commit 就要 111 次 fork）。
    blob = git(root, "log", "--format=%H%x00%s%x00%B%x01", "HEAD")
    pending = []
    for chunk in blob.split("\x01"):
        chunk = chunk.strip("\n")
        if not chunk.strip() or not RESIDUE.search(chunk):
            continue
        sha, subject = chunk.split("\x00")[0], chunk.split("\x00")[1]
        n = int(git(root, "rev-list", "--count", "%s..HEAD" % sha) or 0) + 1
        # 把残文本身也带上：只给 sha 与计数的话，下一个人看不出"要删的是哪一行"，
        # 也就没法判断这条判据扫到的确实是同一形状（而不是巧合命中）。
        first = next((l for l in chunk.split("\x00")[2].split("\n")
                      if l.startswith("MSG;")), "")
        pending.append((sha[:7], n, subject, first.replace("|", "\\|")[:72]))
    pending.sort(key=lambda p: -p[1])

    counts = {"commits_objects": len(allc), "reachable": len(live),
              "unreachable": len(unreachable), "rewritten": len(rows),
              "pending": len(pending), "problems": len(problems),
              "pushed_rewrites": len(pushed_dirty)}
    counts["dry_run"] = sum(1 for r in rows if r[0] == "从未上头")
    counts["was_tip"] = sum(1 for r in rows if r[0] == "已改写")
    counts["tree_bad"] = sum(1 for r in rows if r[0] == "树不等")
    counts["dangling"] = len(dangling)
    # 恒等式：不可达 = 改写配对 + 已归类的悬空。哪一桶漏计，这行就不成立，下面直接判失败
    # （"某类既不算通过也不算失败"是这类分桶最常见的死法）。
    counts["identity_ok"] = (counts["was_tip"] + counts["dry_run"] + counts["tree_bad"]
                             + counts["dangling"] == counts["unreachable"])
    if not counts["identity_ok"]:
        problems.append("分桶恒等式不成立：配对 %d + 悬空 %d != 不可达 %d"
                        % (counts["rewritten"] + counts["dangling"], counts["unreachable"]))

    lines = [
        "# 提交改写映射表（整张表由代码现算，禁止手填）",
        "",
        "- 生成：`python console/_citations.py --rewrite-report --write`",
        "- 核对：`python console/_citations.py --rewrite-report --verify`（不一致退出码 1）",
        "- 实现：`console/_rewrites.py`。**这张表里没有任何一个值是我抄下来的** ——",
        "  前几轮我在同一族上错过三次：注释写死的实测条数与门印出的不一致；",
        "  把 dry-run 造出来的对象当成了活 sha；记下来的\"要重落几个指针\"过一轮就过期。",
        "  所以这次把来源换成对象库 —— 本文件里没有一个手抄的 sha、条数或指针数。",
        "- 这道门自己的成本只印在运行时那行 `[REWRITE_MAP_MATCH]` 读数里（随提交数增长），",
        "  不进这份产物 —— 太贵没人跑的门，最后也会变成说法。",
        "",
        "## 口径（每个数怎么来的）",
        "",
        "| 量 | 值 | 怎么算 |",
        "|---|---|---|",
        # 这里**故意不印** "对象库总数" 与 "可达数" 两个绝对量：它们随每一笔提交变化，
        # 而承载这份产物的那笔提交自己也算一笔 —— 于是"刚 commit 完，表就过期"，
        # --verify 会永远红一次（实测就是这样：objects 133 -> 134）。
        # 只有与"新提交"无关的量才允许进这份产物：不可达数、配对数、欠账数、问题数。
        "| 不可达（旧指针 + 无关悬空对象） | %d | 全量 commit 减去 `rev-list HEAD` 可达集 |"
        % counts["unreachable"],
        "| ├ 改写配对出来的旧指针 | %d | 有同 subject+tree+author 的活对端 |"
        % counts["rewritten"],
        "| │  ├ 曾当过 `main` 的头 | %d | sha 出现在 `git reflog refs/heads/main` |"
        % counts["was_tip"],
        "| │  ├ 从未当过头（dry-run 或被替换的中间父） | %d | 不在 reflog —— 可复验 |"
        % counts["dry_run"],
        "| │  └ 标题/作者同而 tree 不同（改写动了内容） | %d | 放宽 tree 再配一次才叫得出名字 |"
        % counts["tree_bad"],
        "| └ 与改写无关的悬空对象 | %d | `classify_dangling()` 按 stash / 孤儿根归类 |"
        % counts["dangling"],
        "| 恒等式（配对 + 悬空 = 不可达） | %s | 不成立就退出码 1 |"
        % ("成立" if counts["identity_ok"] else "**不成立**"),
        "| 活分支上 message 仍含 `^MSG;` 的条数（欠账） | %d | 一条 `git log --format=%%B` 扫全部；"
        "欠账只进这一行，不进退出码 |" % counts["pending"],
        "| 需要修的问题数 | %d | 非 0 时 `--verify` 退出码 1 |" % counts["problems"],
        "",
        "活集合的口径：%s。" % ("未推的那一段（`%s..HEAD`）" % PUSHED if pushed_ok
                          else "`%s` 这个 ref 当前不在，退回整个 HEAD 可达集" % PUSHED),
        "",
        "## 旧指针 -> 活 sha",
        "",
        "| 来源 | 旧 sha（不可达） | 活 sha | 曾为分支头 | 标题（主键，改写不改它） |",
        "|---|---|---|---|---|",
    ]
    for kind, u, live_sha, subj, tipmark in sorted(
            [r for r in rows if r[0] != "未配对"], key=lambda r: (r[2], r[1])):
        lines.append("| %s | `%s` | `%s` | %s | %s |"
                     % (kind, u[:7], live_sha[:7], tipmark, subj[:58]))
    if dangling:
        lines += ["", "### 与改写无关的不可达对象（点名；不当失败，也不当「没这东西」）", "",
                  "| 旧 sha | 归进哪一类 | 标题 |", "|---|---|---|"]
        lines += ["| `%s` | %s | %s |" % (u[:7], why, subj[:46]) for u, why, subj in dangling]
        # 溯源注：表体是 git 现算的，逐字节比对 ⇒ 任何手改都会让它下次重生时消失。
        # 所以"这个对象是谁造的"只能写在这里 —— 由本文件读回、按 sha 挂到表尾，
        # 于是它既是 git 事实的一部分，又不会在下一次 --write 时被抹掉。
        notes = _load_dangling_notes(root)
        named = {u[:7] for u, _w, _s in dangling}
        for sha in sorted(named & set(notes)):
            lines += ["", "> 溯源注 `%s`：%s" % (sha, notes[sha])]
    lines += ["", "## 还欠的残文（扫出来的，不是我承认的）", ""]
    if pending:
        lines += ["| 坏 sha | 改它要重落几个指针（含它自己） | 残文首行（原样，截 72 字） | 标题 |",
                  "|---|---|---|---|"]
        lines += ["| `%s` | %d | `%s` | %s |" % (s, n, res, t[:52]) for s, n, t, res in pending]
        lines += ["", "指针数每次提交都会变，所以这里只现算、别抄进别处：",
                  "`echo $(( $(git rev-list --count <坏sha>..HEAD) + 1 ))`"]
    else:
        lines += ["（无）：HEAD 可达的 0 条提交的 message 含 `^MSG;`。"]
    lines += ["", "## 为什么引用要靠标题而不是 sha", "",
              "- 改写只动 message 尾部一行，**标题不变**，所以标题是稳定的主键：",
              "  `git log --format=\"%h %s\" | grep -F '<标题片段>'`",
              "- 旧对象只靠 reflog 活着。`git gc` 按 `gc.reflogExpire`（默认约 90 天）回收后，",
              "  这些对象从对象库里消失，`git cat-file -t <旧sha>` 直接失败 —— 届时表里对应的",
              "  **那一整行会不见**（不是变成另一类）。所以这张表不能当永久台账：要长期引用，",
              "  记标题与上面那条 `git log --grep` 复算式。表缩短这件事 `--verify` 兜不住",
              "  （它只核「盘上这份与现在算出来的一致」），兜得住的是恒等式：每次生成时",
              "  「配对 + 悬空 = 不可达」必须成立，不成立直接退出码 1。",
              "- 只能问\"同一位置的新旧两端\"：`git diff --quiet <旧> <活>` 必须 rc=0。",
              "  `git diff <旧> HEAD` 非空**不是缺陷**（那之后还有新工作），别拿它当判据。"]
    if problems:
        lines += ["", "## 问题（这些条不修，`--verify` 就退出码 1）", ""]
        lines += ["- %s" % p for p in problems]
    return "\n".join(lines) + "\n", counts


def main(argv, root=ROOT):
    t0 = time.time()
    text, counts = report(root)
    # 门自己也要报成本：一道没人跑得动的门，最后就变成注释里的说法。
    counts["ms"] = int((time.time() - t0) * 1000)
    out = Path(root) / OUT_REL
    if "--write" in argv:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(text.encode("utf-8"))
        print("已写 %s（旧指针 %d 条 / 无关悬空 %d / 仍欠残文 %d / 问题 %d）"
              % (OUT_REL, counts["rewritten"], counts["dangling"],
                 counts["pending"], counts["problems"]))
        return 0
    if not out.is_file():
        print("[FAIL][REWRITE_MAP_MISSING] %s | fix: python console/_citations.py"
              " --rewrite-report --write" % OUT_REL)
        return 1
    if out.read_bytes() != text.encode("utf-8"):
        print("[FAIL][REWRITE_MAP_STALE] %s differs from what git says now"
              " | fix: python console/_citations.py --rewrite-report --write"
              " —— 表被手改过，或又做过一轮改写没重生" % OUT_REL)
        return 1
    if counts["problems"]:
        print("[FAIL][REWRITE_MAP_PROBLEM] %d 条问题（树不等/配不上对/改写过已推历史）"
              " —— 见表末" % counts["problems"])
        return 1
    if "--verify" in argv:
        print("[REWRITE_MAP_MATCH] objects=%d reachable=%d unreachable=%d pairs=%d pending=%d"
              " problems=0 cost_ms=%d | 表与对象库现算逐字节一致"
              % (counts["commits_objects"], counts["reachable"], counts["unreachable"],
                 counts["rewritten"], counts["pending"], counts["ms"]))
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
