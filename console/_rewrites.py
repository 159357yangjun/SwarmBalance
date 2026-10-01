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


def fields(root, sha):
    return git(root, "show", "-s", "--format=%T%x00%P%x00%an <%ae>%x00%at%x00%s",
               sha).split("\x00")


def classify_dangling(subject, parents):
    """给"配不上对的不可达提交"一个名字，而不是把它当失败。

    不可达 != 改写产物。本仓实测有 17 个不可达 commit，其中只有 12 个是改写造出来的；
    剩下的是 `git stash` 留下的（`On <branch>: …` / `index on <branch>: …` 是它的固定格式）
    和三段孤儿初始提交。**一个都不会红** —— 但要被点到名字：
    把解释不了的悬空对象当"已说明"放过去，就等于给下一次改写留了个隐身位。
    """
    if not parents:
        return "孤儿根提交（另一段历史，无父）"
    if subject.startswith("index on ") or subject.startswith("On "):
        return "git stash 留下的对象（stash ref 已清，对象未回收）"
    return ""


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
        return (git(root, "show", "-s", "--format=%at", s), s)
    unreachable = sorted(allc - live, key=_dkey)
    tips = set(git(root, "reflog", "show", "--format=%H", BRANCH).split())
    # 活集合：优先用"未推的那一段"；`origin/master` 这个 ref 不在（换机器/新克隆）就退回
    # 整个 HEAD 可达集，并在表里说明 —— 这道门不许因为别人仓的状态而误红。
    pushed_ok = git(root, "rev-parse", "--verify", "--quiet", PUSHED) != ""
    range_spec = ("%s..HEAD" % PUSHED) if pushed_ok else "HEAD"
    live_subjects = {}
    for sha in git(root, "rev-list", range_spec).split():
        live_subjects.setdefault(fields(root, sha)[4], []).append(sha)

    rows, problems, pushed_dirty, dangling = [], [], [], []
    for u in unreachable:
        tree, parents, author, ts, subj = fields(root, u)
        cands = [l for l in live_subjects.get(subj, []) if fields(root, l)[0] == tree
                 and fields(root, l)[2] == author and fields(root, l)[3] == ts]
        if not cands:
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
        "- 这道门自己的成本印在 `[REWRITE_MAP_MATCH] … cost_ms=…` 那一行（随提交数增长，",
        "  所以这里也不写数字）—— 太贵没人跑的门，最后也会变成说法。",
        "",
        "## 口径（每个数怎么来的）",
        "",
        "| 量 | 值 | 怎么算 |",
        "|---|---|---|",
        "| 对象库里的 commit 总数 | %d | `git cat-file --batch-all-objects` 按类型筛 |"
        % counts["commits_objects"],
        "| 从 HEAD 可达 | %d | `git rev-list --count HEAD` |" % counts["reachable"],
        "| 不可达（旧指针 + 无关悬空对象） | %d | 上两者之差，逐个按内容分类 |"
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
