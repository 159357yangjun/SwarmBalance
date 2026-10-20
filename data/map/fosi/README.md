# 佛寺镇试验区 GIS 数据

使用现有入口 `python -m console.run --portable`，然后浏览器访问 `http://127.0.0.1:8765/map-lab`。原控制台及杨浦仿真不变。

- 区域：辽宁省阜新市阜新蒙古族自治县佛寺镇参考中心 (121.44231 E, 41.93736 N)，约 5 × 5 km，准确范围见 `region.json`。该区域不是从截图量测的精确边界。
- 首次拉取后，**在线底图**和边界框会直接显示；公共 OSM 图块是按浏览视野正常请求，**不批量下载**。
- 使用本地 GeoJSON 叠加真实建筑/道路时，先手动执行：`python -m pip install osmium shapely`，然后 `python scripts/prepare_fosi_map.py`；再次打开地图页或刷新即可。
- 原始 PBF：Geofabrik 辽宁 <https://download.geofabrik.de/asia/china/liaoning.html>。本地输出目录 `raw/` 和 `output/` 被 Git 忽略，以免误提交第三方大体积数据。
- 版权：© OpenStreetMap contributors，开放数据受 ODbL 约束。
- **重要**：脚本只处理 OSM way，未重建 multipolygon relation，不能将缺失建筑判定为无障碍；GeoJSON 采用经纬度，不能直接作为米制路径计算或碰撞数据。
- 当前阶段仅提供**地图数据预览，不是佛寺镇仿真运行**。后续应独立实现 MapPackage、坐标与覆盖校验、空间索引和固定地图版本，且验证旧杨浦实验零漂移。
