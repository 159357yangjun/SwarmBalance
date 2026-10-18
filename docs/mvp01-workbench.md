# MVP-01 四工作区工作台

目标：从真实保存的项目开始，在四个工作区配置场景和组件、运行既有 Python 仿真、读取并重新打开持久结果。

实现分支从后端 `91af9c75492ee88fc2390a12bcefb8d4589d49ec` 创建。工作台入口是 `/workbench`，原 `/` 控制台保留。HTML、CSS、JS 全部本地提供；没有增加前端框架、CDN 或 Python 依赖。所有工作台业务读写使用 `/api/mvp`，不读取旧会话的 `/api/snapshot`。

## 启动

仓库根目录，准备原有 Python 3.10 虚拟环境和依赖后：

```powershell
$env:PYTHONUTF8='1'
$env:SWARM_BALANCE_MVP_DATA = Join-Path (Get-Location) 'results/mvp-workbench'
.venv310/Scripts/python.exe -m console.run --port 8880 --no-browser
```

浏览器打开 `http://127.0.0.1:8880/workbench`。重启时沿用相同数据目录。该设置独立于历史实验结果，不修改旧仿真配置文件。

## 实际操作

1. 项目区填写名称，点击“保存项目”。新项目采用真实默认配置的完整副本，仅设置快速演示值：3 架同质机、600 步、5 个有限任务、seed 101、greedy 接受概率 1。不会自动创建示例项目或写入结果。
2. 配置区修改机队数量、通用无人机速度/容量/能耗、任务生成、机巢坐标、所有机巢统一泊位、种子和接受概率，再点击“保存配置”。地图固定已有杨浦 OSM。机巢坐标来自已保存配置，没有虚构地图。异构开启时保留原配置机型与配比，通用模型参数只在同质模式消费。
3. 运行区点击“开始真实仿真”，记录实际 `run_id`。进度读取持久状态，每 650ms 轮询；首次加载地图可能暂时为 0。未保存修改时禁止运行。可停止运行；停止或中断保留状态但不提供完整结果。
4. 结果区选择一条历史运行。指标来自所选 `result.snapshot.stats`，输入证据来自 `result.project` 和 `engine_input`；点击“下载结果 JSON”导出完整真实记录。任务表显示引擎 `task_catalog`，包括待分配、执行中与最近 24 个完成任务，完整累计任务数以统计字段为准。
5. 刷新页面会通过本地保存的选择 ID 重新读取项目、运行状态及结果。重启同一服务与数据目录后，仍可在项目列表重新打开历史记录。

API 离线、400/404/409/422 返回可读错误，失败不重置表单。切换项目或新建前提示放弃未保存输入；切换项目/运行使用独立请求代次，迟到响应不覆盖当前结果。页面名称和任务字段在 HTML 渲染前转义。

## 自动检查与实际输出

先运行失败检查：新页面返回 HTTP 404、Node 加载不到 `workbench-core.js`；实现后转绿。随后增加旧项目概率回退与真实任务 `id` 字段检查，先观察缺少辅助函数的失败，再完成实现。

```powershell
$env:PYTHONUTF8='1'
.venv310/Scripts/python.exe -m unittest console.test_mvp_backend console.test_mvp_workbench -v
node --check console/static/workbench.js
```

本次实际执行输出（2026-10-18）：

```text
test_editor_preserves_hidden_config_and_rejects_bad_fields ... ok
test_real_http_serves_workbench_assets_and_keeps_root ... ok
----------------------------------------------------------------------
Ran 24 tests in 15.398s

OK
editor: immutable defaults, full config, numeric validation, stale requests, API errors PASS
```

上述 24 项包括现有后端真实子进程仿真、结果重新打开、参数实际传入、停止、并发轮询与恢复、失败落盘，以及新增真实 HTTP 白名单资源路由和不可变配置编辑检查。`node --check` 退出码 0，无输出。HTTP 测试用动态本地端口与临时数据目录，不依赖已运行的演示服务。Node 不可用时仅该纯前端逻辑检查标记 skip，不能将 skip 视为已验证。

## 交付状态

四区客户端和自动检查已交付；独立浏览器完整操作、重启恢复和平台总体裁决交主控与 AI-R。此文档没有宣称整体 MVP 已 PASS。当前仅支持已有地图、random 数据源和 greedy；没有新增地图编辑、异构配比编辑、批量实验或其他算法。接口契约详见 `docs/mvp01-api.md`。
