# Studio B2 · 将 GIS 预览地图包关联到现有项目（第一条真实资源链路）

> 状态：独立开发 PR（不修改旧仿真运行引擎）；为将来统一 Project/World/Scenario 预留的最小持久资源引用，不是正式 World 模型。
>
> 前置：PR #69 已合并，地图工作区默认以地图为主，功能抽屉按需展开。

## 用户操作

1. 在 `/workbench` 建立并保存现有 MVP 项目。
2. 打开 `/map-lab`，点击顶栏“项目与文件”，读取 `GET /api/mvp/projects` 的真实项目列表，选择项目（复用 `swarm-mvp-project` 当前项目选择）。
3. 在 GIS 工作区框选区域，下载实际 OSM 预览图层；`showPackage()` 读出有效地图包 ID。
4. 在“图层”抽屉中点击“将当前地图包关联到项目”。
5. 后端先使用 MVP 项目服务确认项目存在，再用 GIS 数据服务确认地图包存在、质量字段声明 `simulation_safe=false`，才写入独立的 project preview reference JSON。
6. 用户可选择其他项目，查看它是否各自已有地图预览引用；有引用时可显式打开该地图包，恢复图层与区域。
7. 重启服务后，项目关联信息仍然保留，当前展示图层仍是工作区预览，不默认为某个项目的仿真输入。

## 数据与 API

- `GET /api/gis/project-previews/{project_id}` 返回项目名称、预览地图引用及 `simulation_connected=false`。
- `PUT /api/gis/project-previews/{project_id}` body: `{"package_id":"<24 hex>"}`。
- `data/map/gis/project_previews/{project_id}.json`：临时 + 原子替换写文件；本路径在已有 `.gitignore` 中。
- 只允许现有 MVP 项目 `project_id` 的 32 位小写十六进制 ID，及已存在的 24 位 hash 地图包。拒绝任意磁盘路径、无效项目、无效地图包。
- 一个项目当前保留一个“主 GIS 预览包”引用，替换保留磁盘中的旧 package，未来多资源、历史修订仍需正式 Asset/World 资源目录支持。
- 后端**不写** `results/mvp/projects`、`simulation.json`、`SimSession.osm_path` 或任何旧 Run 状态。

## 限制、风险与后续

- `MapPreviewPackage` 仍只含 OSM ways，未处理完整 multipolygon/DEM，尚不是可信碰撞、飞行路径或三维障碍地图。
- 这个 B2 分支实现的是**真实项目 ↔ 真实地理预览包的持久关联**，不是完整场景编辑功能；当前“项目管理”仍复用 `/workbench`，而不是宣称四页已合并。
- 复杂模型与算法仍在平台功能打通后进行。禁止把 `simulation_connected=false` 改成 true 来冒充仿真就绪。
- 现有 GitHub 地图专项 CI 应覆盖模拟项目隔离、校验、真实路由、不变量；浏览器端真实接口与操作仍需手工走查。
- 下一批应定义正式 Asset catalog、World/Scenario revisions 和项目内对象生命周期；ARCH-06 HOLD 未裁决前不重构 Harness。

## G3 浏览器验收

1. 新建项目 A、B，分别选择地图范围并完成预览包导入。
2. 在 A 中关联地图包，再切换 B，确认 B 未显示 A 的资源引用。
3. 为 B 关联不同的地图包，切回 A，确认独立。
4. 重启服务，确认 A/B 的 GIS 预览关联仍存在。
5. 在 A 中点击“查看项目已关联的地图”，地图范围、图层与 manifest 一致。
6. 下载中断、GIS 缓存缺失、无效项目或失效包时显示错误，不产生伪资源。
7. 从新工作区进入旧杨浦控制台，原杨浦仿真仍不使用这份 GIS 包。
