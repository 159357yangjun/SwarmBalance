"""
适应度评估模块
支持多目标优化和灵活扩展
"""
import math
from typing import Dict, List, Tuple, Callable, Optional


class FitnessEvaluator:
    """适应度评估器，支持自定义目标函数"""
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        初始化评估器
        :param weights: 各目标权重字典
        """
        if weights is None:
            self.weights = {
                'on_time_rate': 0.4,
                'avg_delay': 0.4,
                'energy': 0.2
            }
        else:
            self.weights = weights
        
        # 注册目标函数（可扩展）
        self.objectives: Dict[str, Callable] = {
            'on_time_rate': self._evaluate_on_time_rate,
            'avg_delay': self._evaluate_avg_delay,
            'energy': self._evaluate_energy,
            # 预留扩展空间
            # 'battery_usage': self._evaluate_battery_usage,
            # 'load_balance': self._evaluate_load_balance,
        }
    
    def add_objective(self, name: str, func: Callable, weight: float):
        """
        添加自定义目标函数
        :param name: 目标名称
        :param func: 评估函数
        :param weight: 权重
        """
        self.objectives[name] = func
        self.weights[name] = weight
        self._normalize_weights()
    
    def _normalize_weights(self):
        """归一化权重，使其和为1"""
        total = sum(self.weights.values())
        if total > 0:
            for key in self.weights:
                self.weights[key] /= total
    
    def evaluate(self, schedule_data: Dict) -> Tuple[float, Dict[str, float]]:
        """
        评估调度方案
        :param schedule_data: 调度数据
        :return: (总适应度, 各指标详情)
        """
        metrics = {}
        total_fitness = 0.0
        
        for obj_name, weight in self.weights.items():
            if obj_name in self.objectives:
                value = self.objectives[obj_name](schedule_data)
                metrics[obj_name] = value
                total_fitness += weight * value
        
        metrics['total_fitness'] = total_fitness
        return total_fitness, metrics
    
    def _evaluate_on_time_rate(self, data: Dict) -> float:
        """
        评估准时率
        :param data: 包含任务完成信息的字典
        :return: 归一化准时率 [0, 1]
        """
        completed_tasks = data.get('completed_tasks', [])
        if not completed_tasks:
            return 0.0
        
        on_time_count = sum(1 for task in completed_tasks 
                           if task.get('delay', 0) == 0)
        return on_time_count / len(completed_tasks)
    
    def _evaluate_avg_delay(self, data: Dict) -> float:
        """
        评估平均时延（归一化，越小越好）
        :param data: 包含任务完成信息的字典
        :return: 归一化时延指标 [0, 1]
        """
        completed_tasks = data.get('completed_tasks', [])
        if not completed_tasks:
            return 1.0
        
        total_delay = sum(task.get('delay', 0) for task in completed_tasks)
        avg_delay = total_delay / len(completed_tasks)
        
        # 使用负指数函数归一化（时延越大，得分越低）
        return math.exp(-avg_delay / 1000.0)
    
    def _evaluate_energy(self, data: Dict) -> float:
        """
        评估能耗（预留接口）
        :param data: 包含能耗信息的字典
        :return: 归一化能耗指标 [0, 1]
        """
        total_energy = data.get('total_energy', 0)
        num_drones = data.get('num_drones', 1)
        
        if num_drones == 0:
            return 1.0
        
        avg_energy = total_energy / num_drones
        # 使用负指数函数归一化
        return math.exp(-avg_energy / 100.0)
    
    # 预留扩展方法示例
    def _evaluate_battery_usage(self, data: Dict) -> float:
        """评估电池使用率（预留）"""
        battery_data = data.get('battery_usage', [])
        if not battery_data:
            return 1.0
        # TODO: 实现电池评估逻辑
        return 1.0
    
    def _evaluate_load_balance(self, data: Dict) -> float:
        """评估负载均衡（预留）"""
        drone_loads = data.get('drone_loads', [])
        if not drone_loads:
            return 1.0
        # TODO: 实现负载均衡评估逻辑
        return 1.0


class MultiObjectiveEvaluator(FitnessEvaluator):
    """多目标优化评估器（支持帕累托前沿）"""
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        super().__init__(weights)
        self.pareto_front: List[Dict] = []
    
    def is_dominated(self, solution1: Dict, solution2: Dict) -> bool:
        """
        判断solution1是否被solution2支配
        :param solution1: 方案1的目标值字典
        :param solution2: 方案2的目标值字典
        :return: True if solution1 is dominated by solution2
        """
        better_in_any = False
        for obj_name in self.weights.keys():
            if obj_name not in solution1 or obj_name not in solution2:
                continue
            
            if solution2[obj_name] > solution1[obj_name]:
                better_in_any = True
            elif solution2[obj_name] < solution1[obj_name]:
                return False
        
        return better_in_any
    
    def update_pareto_front(self, new_solution: Dict):
        """
        更新帕累托前沿
        :param new_solution: 新方案的目标值字典
        """
        # 移除被新方案支配的解
        self.pareto_front = [sol for sol in self.pareto_front 
                            if not self.is_dominated(sol, new_solution)]
        
        # 如果新方案不被任何现有方案支配，加入前沿
        if not any(self.is_dominated(new_solution, sol) for sol in self.pareto_front):
            self.pareto_front.append(new_solution)
    
    def get_pareto_front(self) -> List[Dict]:
        """获取当前帕累托前沿"""
        return self.pareto_front
