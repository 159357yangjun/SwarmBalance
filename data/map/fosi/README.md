# 佛寺镇地图：按需选区 OSM 下载和本地缓存（实验版）

- 打开 `python -m console.run --portable --map-lab`，浏览 `http://127.0.0.1:8765/map-lab`。
- 页面里点击 **在地图上选区**，在地图上依次点击两个对角点；也可手动输入 W/S/E/N 坐标，或使用当前视野。默认佛寺镇近似 5 km × 5 km 范围。
- 点击 **准备选区数据**；后台串行访问公共 [Overpass](https://overpass-api.de/api/interpreter)，按约 2.5 km 宽高拆块查询 OSM way，缓存后生成 GeoJSON，刷新无需重新下载。可勾选“强制重新查询”尝试更新。
- 只允许约 **30 km²** 以内的选区；更大面积应使用 Geofabrik 等合规区域原始数据 + 自托管地图数据服务，不能靠公共 Overpass 拼全国地图。
- 运行本地 `requirements.txt` 可直接使用 Shapely；便携模式缺失时 `python -m pip install shapely`。普通浏览不需要该依赖。
- 缓存路径：`data/map/gis/cache/*.json`；只读预览包：`data/map/gis/packages/<package_id>/{manifest.json,*.geojson}`；任务状态：`data/map/gis/jobs/*.json`。全部被 Git 忽略。
- **不自动下载**整省 PBF；旧 `scripts/prepare_fosi_map.py` 仍保留供手动数据处理对比，旧 `data/map/fosi/output` 文件不因新工作流被覆盖。
- 支持排队/下载/处理/完成/失败/取消/重启中断状态。当前每个服务进程只允许同时执行一个导入任务。网络请求取消在当前请求结束后生效。
- 数据源：© OpenStreetMap contributors (ODbL)。页面底图来自在线 OSM 瓦片正常浏览；**不会抓取整片瓦片到本地**。
- 质量边界：仅 `way` 提取，不组装 `relation/multipolygon`，建筑高度可能缺失；未加入 DEM、完整三维建筑、动态禁飞空域。缺失建筑不等于安全空间。`manifest.json` 中 `simulation_safe=false`，严格禁止将本预览包直接视为真三维避障计算地图。
- 它尚未接入新的 World/Scenario/Run 和空间索引；原杨浦地图、已有算法、冻结科研证据均保持不变。
- 服务提供 `POST /api/gis/import-jobs`、`GET /api/gis/import-jobs/{id}`、`POST /api/gis/import-jobs/{id}/cancel`、`GET /api/gis/packages/{id}` 和图层读取接口。

工作流的人工验收：框选 ~1×1 km → 准备 → 进度/图层数量 → 关闭/打开各图层 → 原选区重复准备、命中缓存 → 人为断网/大范围，看到明确错误/边界信息 → 返回原控制台确认不受影响。

当前 CI 只用小型模拟 OSM 响应测试功能和接口，不依赖公共 Overpass 在线稳定性；真实下载需本地验证。
