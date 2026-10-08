# P4：§3(ii) 的拟判据形状被实测驳回的原始证据

## 一手读数（同一棵树、同一解释器，现测）

```
before load: []
after load (NOTHING RUN): ['console.test_swap_time_gate', 'console.test_sla_consumption_gate']
```
⇒ `unittest.defaultTestLoader.loadTestsFromNames([...])` 在**构建 suite 的阶段就把全部成员 import 完**，
一个用例都还没跑。而 #70-P1 那笔污染冻结全局态的时刻恰恰是 **import 期**
（`frontend/environment.py:87 CFG / :100 FLEET_MIX / :105 DEFAULT_NUM_DRONES`）。
⇒ "谁先 import"在用例体内**观察不到**。

## 四次注入全部 STATE_DIFF={}（这就是"永不为红的比较"的证据）

| 注入形状 | 结果 |
|---|---|
| ① 抢先 setenv + 按名字 `import environment`（复刻原污染） | `ran_ab=41 ran_ba=41 rc 两侧同 0`，STATE_DIFF={} |
| ② 往 `sys.modules` 塞共享状态不还原 | 同上，STATE_DIFF={} |
| ③ 断言"我是本批第一个被加载的模块" | 同上，STATE_DIFF={} |
| ④ 断言"前驱是否已在 sys.modules"（用错键：`sys.modules` 存叶子名不是 `console.x`） | 两侧同 fail，STATE_DIFF={} |

⇒ 根因不是注入无效，而是**量具到不了那个时刻**（正是本项目反复出现的那类"读数为 0 要区分真没有 / 量具瞎"）。
另注：①–③ 之所以连真实效应都没有，是因为 #70-P1 已把子集内所有主进程按名字 import 内核迁走 ⇒
子集内不存在"读主进程冻结常量"的用例（`test_r2_destination_without_load.py:27` 里的
`DEFAULT_NUM_DRONES` 只出现在注释中，非可执行语句 —— 已核实）。

## 定稿形状

每个成员**单独起一个进程**、该进程只 import 它自己；两向各跑一整批 ⇒
新成员若依赖前驱留下的全局态，会在自己那一格里红。并加一条前提证人：单加载进程的
`sys.modules` 里**不得出现其它成员名**，否则 `[P4_BLIND]` 红（前提破了不许继续喊绿）。

## 牙的正反两面（本轮实跑）

```
[P4_TEETH_VERDICT] probe_at_head=pass probe_at_tail=fail exit_criterion=(head_state != tail_state)
```
探针 `_p4_teeth_probe_tmp.py` 的两个正例证人也做成了断言：无前驱必须绿（否则恒红夹具）、
有前驱必须红（否则对顺序无感）。文件名不带 `test_` 前缀，避免被 P2(:180)/P3 的 `test_*.py` glob 扫到。

## 清洁树整轮原始输出

见同目录 `A_clean_tree_green_P4.log`：`Ran 3 tests in 115.985s / OK / EXIT=0`，
`ran_ab=40 ran_ba=40 state_diff=0`，两侧 8 个成员 rc 全 0，
`[P4_COST_REAL] … whole_gate_wall_s=116.0 est_vs_measured=2.03`。
