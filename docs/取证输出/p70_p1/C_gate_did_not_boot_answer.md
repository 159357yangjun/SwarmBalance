# 门没跑起来时报红还是静默？（#70-P1 补条：半坏自检实验）

问题原话：**若污染存在但门本身没跑起来（解释器/路径错），它报红还是静默？**
这条不靠推断回答——把三扇门在"缺依赖的解释器"下各跑一次，原始输出留在本目录。

## 实验设置
- 坏解释器：`C:/Users/yyyy/AppData/Local/Programs/Python/Python310/python.exe`
  实测 `import shapely` → `ModuleNotFoundError: No module named 'shapely'`、`fastapi` 同缺。
- 正解释器（项目 venv）：`../.venv310/Scripts/python.exe`（有 shapely/numpy）。
- 命令形状一致，只换解释器：`<python> -m unittest console.test_pN_...`
- ⚠ 未设 `PYTHONIOENCODING=utf-8` ⇒ Windows GBK 控制台，这是评审最容易踩的默认现场。

## 读数（每行都有对应原始日志文件）
| 门 | 缺依赖解释器（A_*） | 退码 | 清洁树+正确解释器（B_*） | 退码 |
|---|---|---|---|---|
| P1 order-independence | `FAILED (failures=1, errors=1)`；内层子进程面另印 `Ran 0 tests ... FAILED (errors=1)` | **1** | `OK` + `[P1_VERDICT] order_ab_rc=0 order_ba_rc=0 optimize_ab=11454 optimize_ba=11454` | 0 |
| P2 name-import 扫描 | `FAILED (errors=2)`，成因是门自己的中文 print 抛 `UnicodeEncodeError` | **1** | `OK` + `[P2_VERDICT] files=49 violations=0 whitelist_stale=0` | 0 |
| P3 residue diff | `FAILED (failures=1)` | **1** | `OK` + `[P3_VERDICT] modules=5 residue_items=0 census_rows=5` | 0 |

**答：三扇都报非零退码，没有一扇静默。**

## 但"红"不等于"看得懂"——本轮实测到的两个真缺陷与修法
1. **P2 的红一开始是自我误伤**：`print("…⇒…")` 里的 U+21D2 在 GBK 下抛 UnicodeEncodeError，
   把 test_A/test_B 双双炸成 ERROR —— 而违规其实是 0。这种红既不是"抓到污染"也不是"通过"，
   属半坏自检。⇒ 修法：每条门**先**印一行纯 ASCII 证人（`[P*_VERDICT] k=v … exit_criterion=…`），
   再印中文说明行。顺序承重：证人必须在可能被编码异常打断的那条 print **之前**。
   现在 A_*（坏解释器）日志里也能看到 `[P2_VERDICT] violations=0` 已落盘 ⇒ 人一眼能分清
   "量具崩了但判定值是 X"与"量具根本没到判定这一步"。
2. **P3 在坏解释器下的那条红是误导性的**：残留项是 `SWARM_BALANCE_SIM_CONFIG` 被指到出厂 config，
   成因是被测模块 import 失败后 setUpClass 半途而废，不是"某模块改了全局态不还原"这个被守的缺陷。
   ⇒ 判据写成 `residue_items==0 AND run_errors==0`：`run_errors` 非空即 [P3_BLIND]（整轮作废），
   不许把"量具没跑起来"当成"发现了残留"或"没问题"。

## 退码判据（写死在册，供复算）
- P1：`(rc_ab==0) and (rc_ba==0) and (optimize_ab==optimize_ba) and (optimize_ab>0)`，否则 1。
- P2：`violations==0 and whitelist_stale==0`，否则 1；扫描器 tokenize/AST 解析失败 ⇒ 直接
  `[P2_BLIND]` 抛错（拿空集合当"查过了、没问题"是最坏的一种绿）。
- P3：`residue_items==0 and run_errors==0`，否则 1；`RESIDUE_JSON` 行缺失 ⇒ `[P3_BLIND]`（退码 1）。
- 共同点：**读不到读数 = 红，不是绿**；三条都在自己那行印出 `exit_criterion=` 便于对账。

## 复算命令
```
# 坏解释器面（预期各自退码 1）
"/c/Users/yyyy/AppData/Local/Programs/Python/Python310/python.exe" -m unittest console.test_p2_no_name_based_kernel_import
"/c/Users/yyyy/AppData/Local/Programs/Python/Python310/python.exe" -m unittest console.test_p3_no_cross_test_residue
"/c/Users/yyyy/AppData/Local/Programs/Python/Python310/python.exe" -m unittest console.test_p1_order_independence_gate
# 清洁面（预期退码 0）
PYTHONIOENCODING=utf-8 ../.venv310/Scripts/python.exe -m unittest console.test_p2_no_name_based_kernel_import
PYTHONIOENCODING=utf-8 ../.venv310/Scripts/python.exe -m unittest console.test_p3_no_cross_test_residue
PYTHONIOENCODING=utf-8 ../.venv310/Scripts/python.exe -m unittest console.test_p1_order_independence_gate
```
原始输出：本目录 `A_gate_did_not_boot_P{1,2,3}.log` / `B_clean_tree_green_P{1,2,3}.log`
（GBK 日志含混排字节，读取请 `tr -d '\0'` 后按二进制容忍查看。）
