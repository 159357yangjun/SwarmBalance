# #69-C2b：drone.py:335-336 载重归零语义审计

基线 674a3c2。**只审计、不改生产码**（drone.py / environment.py 本轮零 diff）。一手证据均来自提交态产物
`docs/取证输出/c1_face_live_fixed.json`（seed 40907 / greedy / 1200）与真实 planner 出口。

## 被审对象

`frontend/drone.py:325-336`，航线跑完最后一个航点弹出后 `if not self.scheduled_position:` 的 else 分支：

```python
self.is_free = True
self.current_load = 0   # :336 任务完成，卸货
self.executing_task_id = None
```

契约：航线清空 ⇒ is_free=True + 载重归零。问题＝#69-C1 送达链已在环境侧逐腿扣减载重后，这条归零是否变成冗余双写；以及"中途清空未送达"是否存在幽灵清零路径。

## 环境侧载重真源（对账基准）

`environment.py` 在 dest 服务航点消费时逐腿扣减：list 分支 :1218-1222、dict 分支 :1227-1231，均为
`current_load = max(0, current_load - task.weight)`。即**每送达一腿就卸一腿的货**。

## 结论①：路由是交错的（非分组）——直接实测

`plan_route_for_tasks`（:1848-1879）按任务循环、每任务追加 `[source-leg…, dest-leg…]`，故多任务链的标签序为交错而非分组。两任务实测：

```
[ROUTE] two-task kinds: ['source', 'dest', 'source', 'dest']
[ROUTE] interleaved (2nd source after 1st dest)? True
```

⇒ 每一腿的送达（+扣减）都发生在下一腿取货之前；不存在"先把 A、B 都装上车再统一送"导致的中途空车误清。

## 结论②：生产轨迹里无幽灵清零路径——per-drone 栈式对账

判据：把每条 `TASK_LOADED` 视为压入该机载重、每条 `TASK_COMPLETION_RECORDED` 视为弹出；在某机 `DRONE_BECAME_FREE`（航线清空 ⇒ 触发 :336）那一刻，若仍有"已装载未完成"的任务残留，则 :336 会静默清掉一份**未送达**的货＝幽灵清零。结果：

```
[RECON] per-drone loads-without-completion still pending at DRONE_BECAME_FREE = 0
[SANITY] TASK_LOADED=40 COMPLETION=38 BECAME_FREE=38
[RECON] completion origins: {'destination_branch': 38}
```

⇒ 38 次转空闲现场，**0** 条载货在航线清空时尚未完成。:336 触发时载重恒已为 0。

## 三态判定：**语义重叠（冗余双写 / 防御性 backstop），建议合并待裁**

- 不是"错误路径"：本轮未发现任何生产可达的幽灵清零（②给 0 计数）。
- 不是纯"合法保险路径"那么无害：它确实与 :1218/:1227 的逐腿扣减**覆盖同一状态**，构成第二处载重写。
- 落点＝**语义重叠**：`drone.py:336` 是 `environment.py` 逐腿扣减之外的兜底归零。当前 seed 下二者一致（载重在到 :336 前已为 0）。

**为何仍不建议贸然删（留给裁定）**：删除后载重真源唯一落在环境侧消费块；一旦将来出现"航线清空但仍有未送达 assignment"的新场景（例如某类提前终止/异常路径），:336 会从"无害兜底"变成"掩盖上游记账缺失的静默清零"——这正是本项目反复踩的"两套到达定义"同族风险。**该风险在当前代码不可达**（②证 0），属前瞻性论证，不作为缺陷量化。

**建议**：保留 :336 但在两处各加一行指向对方的注释锚（drone.py:336 ↔ environment.py:1218），声明"载重真源=环境逐腿扣减，此处仅兜底"；或按裁定合并为单点。本轮不自行改。

## C2b③：mutate 注入器目标重挂（已落地）

旧 `_inject` 按几何 `not has_destination_evidence` 选靶、叙事写"伪造无送达→有送达"——那是 #69-A/C0 cleanup 冒充 delivery 的场景，#69-C1 后生产不再发生。改为按 `record_origin=="destination_branch"` 选一条**合法 dest 完成**复制，诚实命名其证明的窄事实："任意完成被重复计入 ⇒ R3 抓到"。四面复跑：fixed ✅ / mutate(R3=1) ✅RED / forced_cleanup(新门=1,R1=1,R4=1) ✅RED / old(live)[C1_NO_TEETH] ✅RED。

相关：`docs/当前状态真源图.md` §R5/R6、CHANGELOG 2026-10-07 第十三笔。
