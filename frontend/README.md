# Frontend Structure

- `environment.py`: 环境主循环与奖励/指标统计。
- `drone.py`: 无人机实体与电池/运动逻辑。
- `task.py`: 任务实体与任务生成器（TaskGenerator）。
- `charging_station.py`: 充电站实体定义与默认实例。
- `greedy/scheduler.py`: 贪心策略（可直接调用 `greedy_action_from_observation`）。
- `greedy/run_greedy.py`: 纯贪心算法测试入口（`--episodes --episode-steps --csv`）。
- `evaluate_metrics.py`: 统一评估入口（`--policy greedy|pso`），输出对比指标CSV。
- 根配置读取：通过 `config/settings.py` 统一加载 `config/simulation.json`。
- `data/` `assets/` `tools/`: 地图、资源与工具代码。
