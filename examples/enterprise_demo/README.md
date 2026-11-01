# 企业数据接入示例

在项目根目录运行 `python -m examples.enterprise_demo.run`，启动本地 mock 网关并演示快照导入、实时轮询和订单去重。

网关默认使用本地 8765 端口；运行示例时需保证该端口空闲。独立运行网关可执行 `python -m examples.enterprise_demo.mock_gateway 9000`。

此目录只包含示例。正式企业数据源实现在 `swarmbalance/infrastructure/data_sources/enterprise.py`。
