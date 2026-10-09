# 提交改写映射表：GitHub CI 与原开发仓库的验证边界

> 本文件解释 [提交改写映射表](提交改写映射表.md) 的证据范围，不修改原始历史快照。CI 通过不等于在另一台机器重现旧的 reflog、stash 或不可达 commit。2026-10-09 审计。

## 两种证据口径

| 事实 | 完整 GitHub 克隆 | 浅克隆 | 校验政策 |
|---|---|---|---|
| GitHub 当前 HEAD、已获取的祖先提交 | 可重算 | 仅已取得对象可重算 | 可访问部分：Git SHA、标题、可见提交 message 中的 `^MSG;` 残文，错误则红 |
| docs/提交改写映射表.md 的 Markdown 结构、历史 SHA 行集合及内部计数 | 可按归档文本核 | 可按归档文本核 | 两种环境都校验，数字仅视为**原机器快照内部声明** |
| 原开发环境被改写的旧对象与活对象 tree 等价 | 一般不具备旧对象 | 不具备旧对象 | **LOCAL_ONLY / ARCHIVE_ONLY**，CI 不宣称验证 |
| 当过 `refs/heads/main` 头的旧提交及当时 reflog | GitHub 新克隆不携带历史 reflog | 不携带 | **LOCAL_ONLY** |
| `git cat-file --batch-all-objects` 中的悬空对象、已清的 stash、孤儿根 | GitHub 克隆不保留原工作树的所有不可达对象 | 不保留 | **LOCAL_ONLY** |
| `origin/master..HEAD` 的未推分支口径 | 随分支与 fetch 策略变化 | 变化更大 | **不是可移植基线** |
| 原工作树旧改写是否触及某次推送边界 | 无原始 reflog/旧远端快照不可复证 | 不可复证 | **LOCAL_ONLY** |

## 归档表的重复计数为什么不是 52 个唯一对象

快照里列出 **18 条映射行** 和 **34 条悬空说明行**，但 `06eb5a2` 既作为一条消息改写映射，又作为那个被 amend 掉的旧 tip 被归类在悬空说明中。因此 18 + 34 - 1 = **51 个不同旧 SHA**。其中 `已改写=13`、`从未上头=4`、`树不等=0`、消息改写=1。原始生成器计算恒等式时将该消息改写放在悬空桶，不能拿显示的 18 作为互斥分桶数。

可移植门必须检查这一个交集的**语义**（消息改写且标注 amend），不能把任意重复当成允许的例外，也不能改动 51 / 18 / 34 来换取绿灯。

## 消息改写的标题例外

映射表里唯一的 `消息改写` 行为 `06eb5a2 → bd704db`。该类型按定义是 **amend 改了提交标题/消息**，因此归档标题是旧端标题，而活端标题不同属于预期，不可套用普通 `已改写` 行的“标题相同”验证。可移植校验对这条仍硬验活端 SHA 可达，但明确输出 `title_local_only=1`；旧端标题、旧新树与原 reflog 只能由原工作区或专门保存的取证包证明。其他 17 行保持标题一致的硬门。

## 在哪里用哪条命令

- **CI/任意 GitHub 克隆：** `python console/_citations.py --verify --portable-rewrite`。其他文档扫描与产物校验仍为原来的硬门，只有旧改写证据使用可移植口径。
- **单独验证归档：** `python console/_citations.py --rewrite-report --verify --portable`。可在浅克隆运行。对已下载的活 SHA 与标题核对；缺失祖先输出 `REWRITE_HISTORY_PARTIAL`、`live_unavailable`，不会冒充验过。
- **原始开发仓库：** `python console/_citations.py --rewrite-report --verify`，维持旧的**严格逐字节**对象库核对；原始 reflog/不可达对象仍存在时才具有历史意义。
- **禁止 CI 执行：** `--rewrite-report --write`。此操作按 CI 自己的空悬空对象库重生快照，会破坏历史证据。

## 门的红绿含义

可移植绿：归档结构、历史 SHA 去重/交集、分桶数字内部一致；已下载的活端 SHA 与标题一致；已下载的提交 message 中不存在 `^MSG;`。**不证明**旧对象的树相同或原机器 reflog、stash 的真实性。

可移植红：缺失归档、映射行畸形、SHA 重复与错误交叉归类、内部数字不闭合、已取得活端 SHA 标题不符、非浅克隆无法找到活端、当前可见历史有 `^MSG;` 残文。

浅克隆未验证：不可见祖先的 SHA / 标题及其提交 message。必须输出 `REWRITE_HISTORY_PARTIAL`；不能把“没下载到”解释为对象被删除，也不能声称全文提交历史扫描完成。

## 后续取证需求

若要对外证明原工作区的改写过程，必须单独保存经可追溯方式采集的原对象包、旧新两端 SHA/树指纹、当时 refs/reflog 快照与获取环境。GitHub 克隆后验不出这些事实，CI 再绿也不能替代。

## console/test_rewrite_map.py 双模式执行（9 条用例不增减、不无条件 skip）

- `SWARM_REWRITE_TEST_MODE=portable`：默认值，用于 GitHub **depth=1 浅克隆**和 **depth=0 完整历史**。9 条用例全部真实执行：原仓归档结构与可见 SHA 检查、可见提交 message、按可见仓内样本校验批读，以及临时 Git 仓库中的消息改写、tree 不等、残文、确定性、故意改坏产物等正反例。
- `SWARM_REWRITE_TEST_MODE=local`：必须显式指定，仅适用于仍保存旧 commit 对象与 reflog 的**原开发仓库**。对原对象库重新运行原有 `RW.report(ROOT)`、分桶基线与文档 SHA 的严格验证；若证据缺失就**报错**而非退化为 portable。
- 可移植用例的 `DOC_SHA_PORTABLE` 日志分为 `reachable_refs`（实际可取得对象）、`archived_only`（仅归档文本提及）及 `unresolved_not_verified`（无法判断是不是 commit）。后一类不冒充“已验证”；浅克隆不会因为取不到原始提交而被判历史造假。
- 可移植批读门在浅克隆至少取到 HEAD、在完整克隆最多取 20 个可达提交，另强制验证 3 个临时构造的极端标题；原开发仓库的 local 门继续要求大样本（≥40）。
- GitHub Actions 两个 checkout 各运行 `python -m unittest -v console.test_rewrite_map`，均要显示 `Ran 9 tests` 且失败/错误/跳过为 0，不能用仅静态计数代替执行。原开发仓库严格模式暂不能由 GitHub Actions 证明。
