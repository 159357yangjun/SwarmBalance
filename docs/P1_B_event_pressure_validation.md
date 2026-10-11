# P1-B: 独立载货事件链与压力场景验证

本工作仅在 `p1-b-pressure-event-validation` 分支，Draft PR #3。基线为 B 实验 `04937f6d08c11ec14c8c1c47e433d75de5b04ca5`，不触碰 PR #1、PR #2 或 master，不默认开启 B 公式，不覆盖 E0/E1。

## 严格判据

- 同源多任务只能在真实 source 服务事件后全部上机，分别 dest 卸货。
- 异源顺序服务不得提前上机；重复 source 不得重复上机。
- 预判换电中 cargo kg 保留、换电完成恢复路线仍携货。
- 故障（out_of_service）把任务退回原取货点时，无人机的 current_load 与 onboard_load_kg 都必须归零；恢复后不能残留物理货物质量。
- 先执行未修复状态的 8 条硬断言取得 red CI；后续修复需单独提交取得 green CI。正式判定仅据日志，禁止自报通过。

## 压力实验拟采用配置

从仓库 `config/simulation.json` 分别生成独立临时配置，不修改原配置。正常档 `interval_scale=1.0`，较高档 `0.65`，高压档 `0.4`；三档各至少 10 个相同 seeds，严格配对 A+C(assigned) 与 B(onboard)、Greedy、同图同参数。逐 seed 记录完成率、超时、延迟、空载率、耗电 Wh、换电次数、未完成订单。保留数据 JSON/CSV/manifest 与固定 SHA、场景文件哈希，不覆盖历史 E0/E1。完成时再写入真实数字、统计差异与局限。

初始提交只是执行计划与证据边界，不代表上述实验已经运行。
