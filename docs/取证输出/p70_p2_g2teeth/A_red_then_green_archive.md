# 阶段② g2teeth 重标定 — 先红后绿两面原始输出归档

本轮授权要求：**g2teeth 从 skip 转成真实判定前必须先红后绿两面归档**。
这里的"红"不是构造一个永红夹具（#69-H3 裁定①已经否掉过那条路），而是
**对被测生产源码施加真实变异**，看标定门是否变红；随后原样还原，证明绿。

复算命令（三面共用）：
```
cd <repo>
../.venv310/Scripts/python.exe -m unittest -v console.test_g2teeth_calibration
```

---

## 面 A：清洁树 ⇒ 必须绿（实跑）

- 输入状态：`backend_si/pso_scheduler.py` 与 `HEAD` 逐字节一致（未做任何改动）。
- 结果：`Ran 8 tests in 0.238s` / `OK`，退码 0。
- 读数行（原文）：
```
[CAL_TEETH] 变异面生效：阈值 +1（≡`>=`→`>`）使 N==15 从 flush_size=1 变 0；K1 不受影响
[CAL_FROZEN] version=threshold@backend_si/config.yaml:dual_channel.{buffer_size_threshold,emergency_ttl,buffer_timeout} fixtures=K1_below,K2_at,K3_above_once,K4_emergency_not_size,K5_timeout_not_size,K6_mutation_ge_to_gt hashes=pso_scheduler.py=0ecfb9632995;drone.py=84bd484d1836;environment.py=8a6efb782b55
[CAL_ISOLATION] AST 扫描：文件访问型违规=0，import 型违规=0；唯一外部依赖=backend_si\config.yaml
```

## 面 B：对生产源码施加已知变异 ⇒ 必须红（实跑）

- 注入内容（唯一一处，`backend_si/pso_scheduler.py:1444`）：
```python
- if len(self.pending_buffer) >= self.buffer_size_threshold:
+ if len(self.pending_buffer) >  self.buffer_size_threshold:
```
  即把 size 触发口的"含等号"改成"严格大于"——这正是 K2 的标签所断言的那条语义。
- 结果：**两条具名红**，退码非 0。
  1. `[CAL_K2] N=15 == 阈值 15 应恰好开一次 size 口，实得 {'flush_size': 0, ...}`
     —— 标定门自己发现了实现缺陷（判据由被测对象的行为给出，不是我另写一把尺）。
  2. `[CAL_FROZEN]` 那一格转为 `[CAL_FROZEN_DRIFT] 找不到 size 触发口的比较式（原 :1444）`
     —— 冻结三元组的"承重语句仍在"这一面也咬住了同一次变异。
- 意义：这套夹具**有牙**。无牙的标定集会在源码被改坏后照样绿。

## 面 C：还原 ⇒ 复绿（实跑）

- `git diff --numstat -- backend_si/` 为空 ⇒ 还原是逐字节的，不是"看起来一样"。
- 复跑：`Ran 8 tests ... OK`，退码 0（即面 A 的同一段输出）。

## 面 D：解释器/路径坏掉时门报什么（半坏自检面）

标定门自身在 `setUpClass` 里要求真造出一个 scheduler 并读出 TH/TTL/TO；读不到就
`[CAL_BLIND]` 直接失败，而不是静默跳过。另外 g2teeth 侧有一条外派证人
`_assert_calibration_gate_is_live()`：它**实跑**标定子进程并断言四件事同时成立
（`Ran N tests` 存在、`N >= 7`、`returncode == 0`、且输出含 `[CAL_TEETH]`），
任一不成立 ⇒ g2teeth 判红。所以"标定门没跑起来"会被判成**红**，不会被当成通过。

### 面 D 的实测（不是推演）——把证人自己弄坏，看 g2teeth 是否真的拦

注入内容（临时，只动测试文件，生产未碰）：在 `_assert_calibration_gate_is_live()` 首行插入
```python
        raise RuntimeError('SYNTHETIC: calibration gate witness forced to fail')
```
实跑结果：**退码 1，FAILED (errors=1)**，栈顶指向承重调用点：
```
  File "...console/test_speed_fallback_gate.py", line 565, in test_g2teeth_mutation_turns_the_denominator_off
    self._assert_calibration_gate_is_live()
  File "...console/test_speed_fallback_gate.py", line 500, in _assert_calibration_gate_is_live
    raise RuntimeError('SYNTHETIC: calibration gate witness forced to fail')
----------------------------------------------------------------------
Ran 1 test in 40.883s

FAILED (errors=1)
RC=1
```
随后原样还原：工作树与备份 **逐字节相同**（sha256[:12] 两侧均为 `c37b6e125fe9`），
合成字符串计数归 0，临时备份同轮删除。⇒ 这条外包证人是**有牙的**：
它坏掉时 g2teeth 不会留下"没人守着的通过"。


---

## 待验对象没有被当标尺（硬约束自证）

`test_no_experiment_artifacts_are_read` 用 AST 只扫真正的**文件访问调用**与
**import 语句**的字面量参数，匹配 `(^|/)(results|experiments|paper)\b` ⇒ 违规=0。
本门唯一读取的外部文件是 `backend_si/config.yaml`（阈值来源本身）。

注：这条断言曾两次误伤自己（先按全文 grep 打中自己的 docstring，再按字符串字面量
仍打中 docstring）。定稿形状 = 只看"真的会打开文件/真的会导入模块"的那两类节点。
教训登记在 `docs/P70_g2teeth_calibration_plan.md`：**判据必须认得自己扫的是什么**。
