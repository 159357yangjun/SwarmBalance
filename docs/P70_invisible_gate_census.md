# 隐身门普查：为什么 E1 等价门长期红却从没被跑到（一手因果，不修）

基线 79ce795。上位裁定 (二)：**先查清再谈修复，不许直接修**；这条因果决定还有多少同类门同样隐身。

## 1. 主角的门名与盘上证据

| 项 | 值 |
|---|---|
| 文件 | `frontend/test_wind_injection.py`（tracked，最后改动 `1fdd589`） |
| 用例 | `WindInjectionEquivalenceTests.test_every_run_reproduces_e0_bit_for_bit`（`:67`） |
| 断言 | `:79 self.assertEqual(bad, [], "E1+静风未逐字复现 E0（%d 处）…")` |
| 冻结参照 | `results/experiments/e0_baseline_20261002-235335/raw_runs.csv`（`:22 EXP_DIR`，n=6 行） |
| 本轮实跑 | `python -m unittest discover -s frontend -p "test_*.py"` ⇒ `Ran 19 tests in 29.547s / FAILED (failures=1)` |
| 首格差异 | `C1/rep1/从分配到实际装载上机等待时间: E0=46.72641509433962 E1zero=76.90566037735849`（共 12 处） |

⇒ 它**能被发现、能跑、且现在是红的**。所以问题不是"坏掉了看不见"，是"没人跑它"。

## 2. 因果三段（每段都有实测，排除法给出）

主控给的三个候选原因里，**只有第二个成立**。

### ✗ 假设①「discover 模式抓不到」——被实测驳回
```
$ python -m unittest discover -s frontend -p "test_*.py"
Ran 19 tests …            ← 一条不少，说明 discover + pattern 完全能抓到
```
⇒ 命名匹配没问题（两文件都是 `test_*.py`），discover 语义也没问题。**不是这个原因。**

### ✓ 假设②「目录布局：所有聚合入口的起点都在 frontend 之外」——这就是根因
四手证据，全部本轮现读：

1. **常驻分母只列两个目录**：`console/_readme_counts.py:33-36`
   ```python
   TARGETS = (
       ("test_*.py", "console", "console"),
       ("test_*.py", "experiments", "experiments"),
   )
   ```
   ⇒ README 那句"51 文件 / 367 用例"的分母**按构造就装不下 frontend**。
2. **README 给读者的唯一全量命令**是 `README.md:252 python -m unittest discover -s console -p "test_*.py"`。
3. **决定性实测**：`TestLoader().discover('console', top_level_dir='.', pattern='test_*.py')`
   ⇒ `total=367`，其中含 wind 的用例数 = **0**。⇒ 起点写死在 console，物理上够不到隔壁目录。
4. **仓库根也救不了它**：`discover('.', pattern='test_*.py', top_level_dir='.')` ⇒ `total=402`，
   而 `frontend 里的用例是否被 root-discover 抓到: False`。
   原因见 `ls`：**`frontend/` 没有 `__init__.py`**（`console/__init__.py`、`experiments/__init__.py` 都在）
   ⇒ 根 discover 不把该目录当可导入包，整目录被跳过。
   ⇒ 也就是说：**即使有人把聚合起点改成仓库根，这 19 条仍然不会跑** —— 布局这一层比起点更硬。

### ✗ 假设③「历史上有过但被删了」——不成立
`grep -rn "discover -s frontend"` 全仓命中 **2 处，都是我本轮写的文档**（CHANGELOG:16 与
`P70_E1_energy_semantics_freeze_scope.md:39`）。⇒ 历史上没有任何脚本/文档/CI 以 frontend 为起点跑过测试。

## 3. 同类隐身的规模（这才是主控问的那句"还有多少"）

全仓 `test_*.py` 分布（本轮 find，已排除 `__pycache__`/`node_modules`/`paper`）：
```
      1 ./            ← test_build_conclusion_package.py
     51 ./console     ← 进分母
      3 ./experiments ← 进分母
      2 ./frontend    ← 不进分母（本次的主角）
```
⇒ **3 个文件 / 22 条用例在常驻分母之外**（frontend 2 文件 19 例 + 根 1 文件 3 例）。

逐个状态（本轮真跑）：
| 文件 | 单跑结果 | 是否红 | 备注 |
|---|---|---|---|
| `frontend/test_wind_energy.py` | 属上面 19 例之一 | 绿 | B1–B8 结构关系面 |
| `frontend/test_wind_injection.py` | 同上 | **红 1 例** | 即 §1 那条 |
| `test_build_conclusion_package.py`（仓库根） | `Ran 3 tests in 0.566s / OK` | 绿 | 同样不在分母内；`grep` 显示无任何文档引用它 |

⇒ 结论要精确：**隐身的规模是 3 文件 / 22 例，其中当前有 1 例红。**
其余 2 个文件是绿的，但它们同样是"没人跑所以绿不说明任何事"的状态 —— 
和 #69-C5 门禁三分档里 `[P]` 的处境同类：**存在但不被复算**。

## 4. 它在 [G]/[P]/[D] 三档里算哪一档？——答：**根本未接入门禁计数**

`docs/C5_收口与结项.md:36-37` 的定义：`[G]` = 有常驻可执行门（**进 discover、会红**）；
`[P]` = 一次性探针（已删不可复算）；`[D]` = 只是文档声明；且"只有 [G] 计入门禁计数"。

按此定义逐条判：
- 它**不是 [P]**：代码还在、还能跑、没被删；
- 它**不是 [D]**：它有真断言、真基线、真能红；
- 它也**不该记作 [G]**：[G] 的条件是"进 discover"，而 §2 证明没有任何聚合入口进得到它。
- ⇒ 准确定性 = **"具备 [G] 的实现、处于 [G] 之外的接线"**，即**从未接入门禁计数**。
  `grep -n "wind" docs/C5_收口与结项.md` → **无输出**：门禁总表里连一行都没有，既没进 2-A 也没进 2-B。

⚠ 更要紧的一条：`docs/模型真实结构修订.md:20` 写着
「`wind` … **zero-wind 逐 run == E0 已验证**」，引用出处正是这条现在红的门。
⇒ 这是一句 **[D] 级对外结论，站在一条无人跑的 [G]-shaped 门上，且该门当前为假**。
按本仓纪律（"符号存在≠接线"、"验证方向要写进标签"），这句必须挂 pending revalidation。

## 5. 建议的处置顺序（等裁，本轮一律不动）

1. **不要先修那条红**（主控已明令）。它的红可能是正确的修复后果（D-iv 改了 completion/assignment 时序），
   也可能是真缺陷 —— 分不清，因为没做受控消融。
2. 先做**接线**：把 frontend 纳入某个聚合入口（三条路：给它加 `__init__.py` / 在 `_readme_counts.TARGETS`
   加一项 / 在 README 增加第二条显式命令并让某常驻门去跑它）。接线本身不改判据、不改生产语义。
3. 再接着做**受控消融**定性质：`3c54c37^` vs HEAD 各跑同一预设 → 若确由 D-iv 引起，按 #69-H3 先例
   登记"E0 冻结基线已被正确修复作废"并**重生成基线**，而不是放宽等价门。
4. 顺手处理同批隐身的另外 3 例（`test_build_conclusion_package.py`，当前绿，但同样无人复算）。

复算本文所有断言：
```bash
python -m unittest discover -s frontend -p "test_*.py"        # Ran 19 / FAILED(failures=1)
python -m unittest discover -s . -p "test_build*.py" -t .     # Ran 3 / OK
python -c "import unittest;print(unittest.TestLoader().discover('console',top_level_dir='.',pattern='test_*.py').countTestCases())"   # 367
ls console/__init__.py experiments/__init__.py frontend/__init__.py   # 第三个不存在
grep -n "TARGETS = (" -A 3 console/_readme_counts.py
grep -n "wind" docs/C5_收口与结项.md                                   # 空
```

---

## 6. 接线已做（主控裁定②：放行接线、不含修复）——选的是路径②，不是建议的路径①

主控建议加 `frontend/__init__.py`（"同时修好另外两个隐身文件"）。**实测后改选了另一条**，理由是一手副作用：

```
$ touch frontend/__init__.py
$ python -m unittest discover -s . -p "test_wind*.py" -t .
Ran 20 tests … FAILED (failures=1, errors=1)      ← 多出一个 error
ERROR: frontend.greedy (unittest.loader._FailedTest)
  File ".../frontend/greedy/scheduler.py", line 6, in <module>   ← 扁平 import 在包语境下断
```
⇒ 加了 `__init__.py` 之后 discover 会把 `frontend/greedy/` 当子包去导入，而它内部用的是扁平 import
（`environment.py:14-25` 同样是 `from drone import …` 这种），于是**新造出一个坏模块**。
⇒ 而且它只解决"根 discover 进得去"，并不把 frontend 带进 `_readme_counts` 的分母。
⇒ 试探用的 `__init__.py` 已删除（`ls` 复核不存在）。

**实际采用的接线路径 = 给 `_readme_counts` 增加第三个 TARGETS 项 + 让 top_level_dir 可显式指定**：

| 改动 | 为什么必须一起改 |
|---|---|
| `TARGETS += ("test_*.py", "frontend", "frontend")` | 分母此前按构造装不下 frontend |
| `_CHILD` 的 `top_level_dir` 从写死 `str(top)` 改为可传入 | **不加这一条，光加 TARGETS 会让工具自己红**：`discover('frontend', top_level_dir='.')` 实测抛 `ImportError: Start directory is not importable` |
| README 三处计数字位**改为自带目录名**（`# console: 51 个文件 / 367 个用例`） | 旧 verify 是 `zip(claims, rows)` **位置式**配对 ⇒ 我插入 frontend 那一位后，experiments 被顶偏，报出 "experiments/：README 写 2 个文件 / 19 个用例" —— **那是误配不是漂移**，但长得太像真漂移，很容易被下一个人当"数字过期"直接 `--fix` 覆盖掉 |
| `fix()` 同样改为按标签定位；命中数 ≠ 1 时**拒绝猜位置并返回 1** | 否则 --fix 会把误配写回盘上，把错的数据变成"看起来一致" |
| `console/test_readme_counts.py::test_measure_is_not_vacuous` 的 `len(rows)==2` → 与 `len(TARGETS)` 对账 + 下限 ≥3 | 钉死 2 会让"加一个目录"必须顺手改这里；改成对账后，**有人摘掉 frontend 会当场红** |
| 同文件加**顺序判别式**：把三段声明整体倒序重排后仍须逐目录对上 | 位置式实现在这一步必然红 ⇒ 证明现在吃的确实是标签而不是位置 |

### 新分母（本轮现算，非推算）

```
[OK] README 测试计数与实测一致（console=51文件/367用例；experiments=3文件/32用例；frontend=2文件/19用例）
```
⇒ **367 → 386 例（+19）**，文件 51 → 53。主控问的"预期 367→?"答：**386**（若只算 console 那一路仍是 367，因为 frontend 的 19 例走的是独立一条 discover，不并入 console 那条命令）。

### 接线后的关键不变量：那例红**仍然是红**

```
$ python -m unittest discover -s frontend -t frontend -p "test_wind*.py"
Ran 19 tests in 15.904s
FAILED (failures=1)          ← 与接线前同一格、同一个差异清单（12 处）
```
⇒ 遵守裁定"**不得为了让那例绿而改判据或改基线**"：我没动 `test_wind_injection.py`、没动 E0 基线、
没动任何断言。接线只是让它**从此会被跑到**。

### 顺带被咬到的一处（同轮，属注释插入的代价）

我给 `drone.py` 加口径注释把文件推下 5 行，`_citations --verify` 当场报
`ANCHOR_MISS docs/数据来源与可追溯性登记表.md:41 frontend/drone.py:206#不再使用`（真值现为 :211）
⇒ 只改引用不改判据。**这已是本仓第 N 次由行号引用漂出来的红**，登记在此是为了说明：
往生产文件插注释也会触发同一把门，不只是改 README 才会。
