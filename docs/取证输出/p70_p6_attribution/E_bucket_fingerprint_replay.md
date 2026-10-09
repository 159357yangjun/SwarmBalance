# 磁盘缓存消融：桶指纹现算 + 时间线（第四十二笔）

## 1. 结构事实（实测，不是推断）

在临时 worktree（`git worktree add --detach <tmp> HEAD`）里 import `tools.osm`，打印其 `_CACHE_DIR`：

```
_CACHE_DIR = C:\Users\yyyy\AppData\Roaming\TRAE SOLO CN\...\drone-scheduling\frontend\data\.osm_cache
exists = True
```

⇒ **worktree 不隔离缓存**：它落到主仓那一份。裁定要求的"混淆源存在"这一条成立。

## 2. 但缓存解释不了那 12 格 —— 两条反证

### 反证 A：跨 A* 搬家的那一对反而逐格相同
`e0_baseline_20261002-235335`(10-02) 与 `e0_baseline_20261003-230126`(10-04) 之间隔着 `c0af7c7`（A* 本体从 environment.py 抽到 route_planner.py）。
两批在门比较的列区间 `[10:]` 上 **0 格差**（只有 `耗时秒` 6 格漂）。若缓存能改变通行判定，这一对最该先表现出不一致。

### 反证 B：仿真几何桶的首写时间晚于 OLD 那批的生成时间
```
10-08 21:23:23  pathclear-126d6706d9de871d.pkl        58 B   （合成小桶）
10-08 21:23:23  pathclear-7fc8db19af0e5793.pkl        58 B
10-08 21:23:23  pathclear-917633f3f52c4220.pkl        58 B
10-08 21:23:23  pathclear-d6528db99350831b.pkl        58 B
10-08 21:23:24  pathclear-1a34c75dc7d88129.pkl     5,218,567 B
10-08 21:57:01  pathclear-90753a7a442897a4.pkl     2,406,258 B   ← 仿真几何桶
```
OLD 那批产于 **10-02 23:53**，而仿真几何桶 `90753a7a…` 今天 21:2x 才第一次出现 ⇒ OLD 不可能读到今天的内容。

### 反证 C：三个 commit 的桶指纹相同
按 `_path_clear_bucket()` 的原式（高楼 WKT + no_fly enabled/n + 每个 zone 的 name|margin|WKT，md5[:16]）现算：

| commit | high buildings | no_fly | zones | 桶指纹 |
|---|---|---|---|---|
| `c0af7c7` | 18 | enabled=True | 2 | `90753a7a442897a4` |
| `3f80a17` | 18 | enabled=True | 2 | `90753a7a442897a4` |
| HEAD(5642baa) | 18 | enabled=True | 2 | `90753a7a442897a4` |

⇒ 障碍几何本身在这三点上没有可检出的差异；配置侧 `reserve_margin_m` 自始为 15.0（`git log -S` 只命中初始提交），
`a6018a6` 给 simulation.json 加的 `reach_weight` 默认 0.0 且不在 pin 清单内。

## 3. 因此没有执行"删缓存再重跑"

删一份 19 MB 共享缓存只会让下一次跑变慢，**不产生任何新读数**（三条反证已经把缓存排除）。
按纪律：消融要抽掉的是**能影响读数的混淆源**；这里已证明它不影响，故不做无意义的破坏性步骤。

## 4. 顺带查出（登记，未修）

仿真几何桶 `pathclear-90753a7a442897a4.pkl` 内含 **2 条合成坐标键**：
`((0.0, 0.0), (1.0, 1.0)) -> True`、`((0.0, 0.0), (2.0, 2.0)) -> True`。
真实仿真键的坐标量级是 x≈3.5e5 / y≈3.4e6，这两条来自避障探针 ⇒ **测试写入与仿真持久状态共用同一命名空间**。
本次无害（那些点对不会在真实回合中出现），但没有隔离。属新范围，见 CHANGELOG 第四十二笔残余边界 (iv)。

## 5. 复算

```bash
# 桶指纹（在任意 commit 的工作副本里跑，需 SWARM_BALANCE_PATHCLEAR_CACHE=0 以免污染）
python - <<'PY'
import sys, os, pathlib, hashlib
wt = pathlib.Path(".").resolve()
sys.path.insert(0, str(wt)); sys.path.insert(0, str(wt/"frontend"))
os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(wt/"config"/"simulation.json")
from tools.osm import load_map_data
from no_fly_zone import get_no_fly_zones
_, bs = load_map_data(str(wt/"frontend"/"data"/"map"/"part_of_yangpu.osm"))
hi = [b for b in bs if b.get("height") and b["height"] > 20]
nf = get_no_fly_zones(); zones = list(getattr(nf, "zones", None) or [])
parts = ["B%d" % len(hi)] + [g["geometry"].wkt for g in hi]
parts.append("NF enabled=%d n=%d" % (int(bool(getattr(nf, "enabled", False))), len(zones)))
parts += ["%s|%r|%s" % (z.name, getattr(z, "margin", None), z.geometry.wkt) for z in zones]
print(hashlib.md5("\n".join(parts).encode("utf-8")).hexdigest()[:16])
PY

# 合成键普查
python - <<'PY'
import pickle
with open("frontend/data/.osm_cache/pathclear-90753a7a442897a4.pkl","rb") as fh: b = pickle.load(fh)
print([k for k in b if max(abs(x) for x in k[0]+k[1]) <= 10])
PY
```
