# P70 阶段⑤c · E0 基线重生成的三方对照读数（2026-10-08）

本轮不写结论段，只把**测到的东西**按形状摆出来。所有数字来自本轮真跑，复算命令在文末。

## 一、四个参照物

| 简称 | 目录 | git_commit | pin 与盘上相符 | 状态 |
|---|---|---|---|---|
| OLD | `e0_baseline_20261002-235335` | `1c790a0…` | **12/16** | 已入库，原样保留（未删、未改名） |
| OCT3 | `e0_baseline_20261003-230126` | `a298d6d…` | 12/16 | 已入库，本轮才发现它存在（同预设的第二批） |
| NEW | `e0_baseline_20261008-210053` | `d19d647…` | **16/16** | 本轮生成并入库 |
| NEW2 | 临时目录里的同命令第二遍 | `d19d647…` | — | 只用于自一致性测量，未入库 |

## 二、逐格对照（比较范围 = 门自己取的列区间 `list(header)[10:]`，共 24 列 × 6 行 = 144 格）

| 对照 | 差异格数 | 涉及列 |
|---|---|---|
| NEW vs OLD | **12** | `从分配到实际装载上机等待时间`(6)、`从上机到送达平均时间`(6) |
| NEW vs OCT3 | **12** | 同上两列，且数值与 OLD 完全一致 |
| OLD vs OCT3 | **0** | （全表只有 `耗时秒` 6 格不同，它在 `[10:]` 之外，不进门的比较） |
| NEW vs NEW2 | **0** | （同样只有 `耗时秒` 6 格漂：2.2043↔2.105、2.4481↔2.3444 …） |

NEW vs OLD 的具体值（每列取前两格，其余四格同方向）：

```
C1/rep1  从分配到实际装载上机等待时间  OLD=46.72641509433962   NEW=76.90566037735849
C2/rep1  从分配到实际装载上机等待时间  OLD=42.71621621621622   NEW=78.56756756756756
C1/rep1  从上机到送达平均时间          OLD=152.56603773584905  NEW=122.38679245283019
C2/rep1  从上机到送达平均时间          OLD=145.94594594594594  NEW=110.09459459459460
```

## 三、这把门的两端（先红后绿，同一棵树、同一命令，只换参照目录名）

| 参照 | 结果 |
|---|---|
| OLD | `FAILED` —「E1+静风未逐字复现 E0（**12 处**）」 |
| NEW | `Ran 9 tests OK`（frontend 全套件：等价门 3 + 符号门 4 + 非零风行为门 2） |

## 四、这组读数支持什么、不支持什么

支持：
- NEW 是**当前树上可复现的**产物（NEW vs NEW2 在比较范围内 0 差）。
- OLD 与 OCT3 互相一致 ⇒ "10-02 那批不是孤立噪声"。
- 因此 NEW 与 OLD/OCT3 的 12 格差**不是新基线跑坏了**，也不是随机波动（随机性已被 NEW vs NEW2 排除）。

不支持（本轮明确没做）：
- **不支持**"这 12 格由某一次具体改动造成"的归因 —— 消融未做，不在授权内。
- **不支持**把 zero-wind 说成"从未成立"：对 NEW 它逐字成立。
- **不支持**任何 Wh/km 对外表述（E1 载重惩罚归属口径仍未定，见 `docs/P70_E1_load_penalty_attribution_two_readings.md`）。

一个必须点名的形状问题：OLD 与 OCT3 在这两列上一致、而 NEW 与它们都不同，
说明差异发生在 `a298d6d` 之后、`d19d647` 之前的某处；但**本轮没有证据说是哪一处**，
所以这里只登记为待裁 (iii)，不写成结论。

## 五、复算命令

```bash
# 1) 新基线指纹自洽（应得 16 / 16）
python -c "import json,io,hashlib,pathlib;d=json.load(io.open('results/experiments/e0_baseline_20261008-210053/reproducibility.json',encoding='utf-8'));p=d['core_source_sha256'];print(sum(1 for k,v in p.items() if pathlib.Path(k).is_file() and hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest()==v),'/',len(p))"

# 2) 生成命令原文（输出根给临时目录时才可用；装入前已验证）
python -m experiments.runner --preset experiments/presets/e0_baseline.yaml --output-root <TMP>

# 3) 等价门（当前指 NEW，应绿）
python -m unittest discover -s frontend -t frontend -p "test_*.py"

# 4) 逐格对照：把两份 raw_runs.csv 的 list(header)[10:] 区间逐格比
#    （门的取列方式见 frontend/test_wind_injection.py 的 metrics = keys[10:]）
```

原始日志：本目录 `A_generation_run_first.log`、`B_generation_run_second.log`、`C_equivalence_gate_green.log`。
