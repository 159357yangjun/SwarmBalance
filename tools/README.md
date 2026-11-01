# 独立数据处理工具

`zip_range_extract.py` 使用 Python 标准库，通过 HTTP Range 从 ZIP 提取指定成员并检查 CRC32。它不是 Web 服务模块，不会在启动控制台时运行。

在项目根目录执行：

```powershell
# 列出脚本中登记的数据集里的 ULog 成员（会访问网络）
.venv310/Scripts/python.exe tools/zip_range_extract.py

# 传入已列出的成员名或其后缀，将匹配成员写入 data/raw/px4_logs/ulg/
.venv310/Scripts/python.exe tools/zip_range_extract.py <member-name>
```

目标数据集 URL 保留在脚本中；上游可用性需使用时验证。原数据说明和许可证在 `data/raw/px4_logs/`。内核运行所需的 OSM 解析器仍在 `frontend/tools/osm.py`。
