"""
任务列表实时展示窗口 - 多进程架构
使用tkinter在独立进程中展示任务列表，主程序运行不受影响
"""

import tkinter as tk
from tkinter import ttk
import multiprocessing as mp
import time
import threading


# 状态颜色配置
STATUS_COLORS = {
    'pending': '#FFA500',      # 橙色 - 待分配
    'assigned': '#4169E1',     # 蓝色 - 已分配
    'in_progress': '#32CD32',  # 绿色 - 执行中
    'completed': '#808080',    # 灰色 - 已完成
    'failed': '#FF4444',       # 红色 - 失败
}

STATUS_NAMES = {
    'pending': 'Pending',
    'assigned': 'Assigned',
    'in_progress': 'In Progress',
    'completed': 'Completed',
    'failed': 'Failed',
}

PRIORITY_COLORS = {
    3: '#FF0000',  # 红色 - 最高优先
    2: '#FFCC00',  # 黄色 - 中等优先
    1: '#00CC00',  # 绿色 - 最低优先
}


class TaskShowerWindow:
    """任务列表展示窗口"""

    def __init__(self, queue, update_interval=0.5):
        self.queue = queue
        self.update_interval = update_interval
        self.root = None
        self.task_items = {}  # 存储任务列表项 {task_id: tree_item}
        self.completed_tasks = []  # 已完成任务历史

    def start(self):
        """启动tkinter主循环"""
        self.root = tk.Tk()
        self.root.title("Drone Scheduling - Task Monitor")
        self.root.geometry("900x600")
        self.root.minsize(700, 400)

        # 设置主题色
        self.root.configure(bg='#2b2b2b')

        self._create_widgets()
        self._start_update_loop()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _create_widgets(self):
        """创建UI组件"""
        # 标题栏
        header_frame = tk.Frame(self.root, bg='#1e1e1e', height=60)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        header_frame.pack_propagate(False)

        title_label = tk.Label(
            header_frame,
            text="Task Monitor",
            font=("Microsoft YaHei UI", 18, "bold"),
            fg="#ffffff",
            bg="#1e1e1e"
        )
        title_label.pack(side=tk.LEFT, padx=20, pady=15)

        # Stats label
        self.stats_label = tk.Label(
            header_frame,
            text="Updating...",
            font=("Microsoft YaHei UI", 10),
            fg="#888888",
            bg="#1e1e1e",
            anchor='e'
        )
        self.stats_label.pack(side=tk.RIGHT, padx=20, pady=15)

        # 主内容区域
        content_frame = tk.Frame(self.root, bg='#2b2b2b')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧：未完成任务列表
        left_frame = tk.Frame(content_frame, bg='#2b2b2b')
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 未完成任务标签
        active_label = tk.Label(
            left_frame,
            text="Current Tasks",
            font=("Microsoft YaHei UI", 12, "bold"),
            fg="#ffffff",
            bg="#2b2b2b"
        )
        active_label.pack(anchor='w', pady=(0, 5))

        # 任务列表容器
        tree_frame = tk.Frame(left_frame, bg='#2b2b2b')
        tree_frame.pack(fill=tk.BOTH, expand=True)

        # 创建Treeview
        columns = ('id', 'priority', 'status', 'deadline', 'remaining', 'weight')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=15)

        # Set columns
        self.tree.heading('id', text='Task ID')
        self.tree.heading('priority', text='Priority')
        self.tree.heading('status', text='Status')
        self.tree.heading('deadline', text='Deadline')
        self.tree.heading('remaining', text='Remaining')
        self.tree.heading('weight', text='Weight(kg)')

        self.tree.column('id', width=100, anchor='w')
        self.tree.column('priority', width=70, anchor='center')
        self.tree.column('status', width=80, anchor='center')
        self.tree.column('deadline', width=80, anchor='center')
        self.tree.column('remaining', width=80, anchor='center')
        self.tree.column('weight', width=70, anchor='center')

        # 设置样式
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "Treeview",
            background="#3c3c3c",
            foreground="#ffffff",
            fieldbackground="#3c3c3c",
            rowheight=28
        )
        style.configure(
            "Treeview.Heading",
            background="#4a4a4a",
            foreground="#ffffff",
            font=("Microsoft YaHei UI", 10, "bold")
        )
        style.map("Treeview", background=[('selected', '#5a5a5a')])

        # 滚动条
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 右侧：统计信息面板
        right_frame = tk.Frame(content_frame, bg='#2b2b2b', width=280)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(10, 0))
        right_frame.pack_propagate(False)

        # Stats panel title
        stats_title = tk.Label(
            right_frame,
            text="Real-time Stats",
            font=("Microsoft YaHei UI", 12, "bold"),
            fg="#ffffff",
            bg="#2b2b2b"
        )
        stats_title.pack(anchor='w', pady=(0, 10))

        # 统计信息容器
        self.stats_frame = tk.Frame(right_frame, bg='#2b2b2b')
        self.stats_frame.pack(fill=tk.X, pady=5)

        # 创建统计卡片
        self._create_stat_cards()

        # Legend
        legend_frame = tk.LabelFrame(
            right_frame,
            text=" Status Legend ",
            bg='#2b2b2b',
            fg='#888888',
            font=("Microsoft YaHei UI", 10),
            padx=10,
            pady=10
        )
        legend_frame.pack(fill=tk.X, pady=(20, 0))

        for status, color in STATUS_COLORS.items():
            row = tk.Frame(legend_frame, bg='#2b2b2b')
            row.pack(fill=tk.X, pady=2)
            color_box = tk.Frame(row, bg=color, width=20, height=16)
            color_box.pack(side=tk.LEFT, padx=(0, 10))
            tk.Label(row, text=STATUS_NAMES.get(status, status), bg='#2b2b2b', fg='#cccccc').pack(side=tk.LEFT)

    def _create_stat_cards(self):
        """创建统计卡片"""
        self.stat_labels = {}

        stats = [
            ('pending_count', 'Pending Tasks', '#FFA500'),
            ('assigned_count', 'In Progress', '#4169E1'),
            ('completed_count', 'Completed', '#32CD32'),
            ('total_tasks', 'Total Tasks', '#ffffff'),
            ('current_time', 'Current Time', '#00CED1'),
            ('free_drones', 'Free Drones', '#90EE90'),
            ('busy_drones', 'Busy Drones', '#FF6B6B'),
            ('is_peak', 'Peak Phase', '#FF4444'),
        ]

        for key, label, color in stats:
            card = tk.Frame(self.stats_frame, bg='#333333', padx=10, pady=8)
            card.pack(fill=tk.X, pady=3)

            tk.Label(
                card,
                text=label,
                font=("Microsoft YaHei UI", 9),
                bg='#333333',
                fg='#888888'
            ).pack(anchor='w')

            self.stat_labels[key] = tk.Label(
                card,
                text="0",
                font=("Microsoft YaHei UI", 16, "bold"),
                bg='#333333',
                fg=color
            )
            self.stat_labels[key].pack(anchor='w')

    def _start_update_loop(self):
        """启动数据更新循环"""
        self._update()

    def _update(self):
        """从队列获取数据并更新UI"""
        try:
            while True:
                data = self.queue.get_nowait()
                if data is None:  # 收到结束信号
                    self.root.quit()
                    return
                self._process_data(data)
        except:
            pass  # 队列为空，继续

        # 安排下一次更新
        self.root.after(int(self.update_interval * 1000), self._update)

    def _process_data(self, data):
        """处理接收到的数据"""
        if not data:
            return

        # 更新统计数据
        self._update_stats(data)

        # 获取任务数据
        tasks = data.get('tasks', [])
        drone_tasks = data.get('drone_tasks', [])  # 无人机正在执行的任务

        # 合并所有任务（未分配 + 执行中）
        all_tasks = {}

        # 添加未分配任务
        for task in tasks:
            task_id = task.get('task_id', '')
            all_tasks[task_id] = {
                'task_id': task_id,
                'status': 'pending',
                'priority': task.get('priority', 1),
                'deadline': task.get('remaining_time', float('inf')),
                'weight': task.get('weight', 0),
            }

        # 添加执行中任务（无人机正在执行的任务）
        for dt in drone_tasks:
            task_id = dt.get('task_id', '')
            if task_id:
                all_tasks[f"[In Progress] {task_id}"] = {
                    'task_id': f"[In Progress] {task_id}",
                    'status': 'in_progress',
                    'priority': dt.get('priority', 1),
                    'deadline': dt.get('remaining_time', float('inf')),
                    'weight': dt.get('weight', 0),
                    'drone': dt.get('drone_id', ''),
                }

        # 更新列表
        self._update_task_list(all_tasks)

    def _update_stats(self, data):
        """更新统计信息"""
        # 更新统计标签
        self.stat_labels['current_time'].config(text=f"{data.get('current_time', 0)}")
        self.stat_labels['pending_count'].config(text=f"{len(data.get('tasks', []))}")

        # 计算执行中的任务数
        in_progress = len(data.get('drone_tasks', []))
        self.stat_labels['assigned_count'].config(text=str(in_progress))

        # 累计完成数
        self.stat_labels['completed_count'].config(text=str(data.get('completed_count', 0)))

        # 总任务数
        self.stat_labels['total_tasks'].config(text=str(data.get('total_tasks', 0)))

        # 无人机状态
        self.stat_labels['free_drones'].config(text=str(data.get('free_drones', 0)))
        self.stat_labels['busy_drones'].config(text=str(data.get('busy_drones', 0)))

        # Peak 状态
        is_peak = data.get('is_peak')
        if is_peak is None:
            # constant 模式
            self.stat_labels['is_peak'].config(text="N/A")
            self.stat_labels['is_peak'].config(fg='#888888')
        elif is_peak:
            self.stat_labels['is_peak'].config(text="YES")
            self.stat_labels['is_peak'].config(fg='#FF4444')
        else:
            self.stat_labels['is_peak'].config(text="NO")
            self.stat_labels['is_peak'].config(fg='#32CD32')

    def _update_task_list(self, tasks):
        """更新任务列表"""
        # 清空现有项
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 按优先级排序（高优先级在前）
        sorted_tasks = sorted(
            tasks.values(),
            key=lambda x: (-x.get('priority', 1), x.get('deadline', float('inf')))
        )

        # 添加任务
        for task in sorted_tasks:
            priority = task.get('priority', 1)
            status = task.get('status', 'pending')
            deadline = task.get('deadline', float('inf'))

            # 优先级标签
            priority_text = f"⭐" * priority

            # 状态标签
            status_text = STATUS_NAMES.get(status, status)

            # 剩余时间
            if deadline == float('inf'):
                remaining = "∞"
            else:
                remaining = f"{int(deadline)}"

            # 设置行颜色标签
            if status == 'pending':
                tag = 'pending'
            elif status == 'in_progress':
                tag = 'progress'
            else:
                tag = ''

            self.tree.insert(
                '',
                'end',
                values=(
                    task.get('task_id', ''),
                    priority_text,
                    status_text,
                    f"{int(deadline) if deadline != float('inf') else '∞'}",
                    remaining,
                    task.get('weight', 0)
                ),
                tags=(tag,)
            )

        # 配置标签颜色
        self.tree.tag_configure('pending', background='#3d3d00')
        self.tree.tag_configure('progress', background='#003300')

    def _on_close(self):
        """窗口关闭事件"""
        # 只销毁窗口，不影响主进程
        self.root.destroy()


def run_task_shower_process(queue, update_interval=0.5):
    """在子进程中运行任务展示窗口"""
    window = TaskShowerWindow(queue, update_interval)
    try:
        window.start()
    except Exception as e:
        print(f"Task shower window error: {e}")


class TaskShowerManager:
    """任务展示管理器 - 用于主进程控制子进程窗口"""

    def __init__(self, update_interval=0.5):
        self.queue = mp.Queue()
        self.process = None
        self.update_interval = update_interval
        self._running = False

    def start(self):
        """启动任务展示窗口进程"""
        if self.process is not None and self.process.is_alive():
            return

        self.process = mp.Process(
            target=run_task_shower_process,
            args=(self.queue, self.update_interval),
            daemon=True
        )
        self.process.start()
        self._running = True
        print("[TaskShower] Task Monitor window started")

    def update(self, tasks_data):
        """发送任务数据到展示窗口"""
        if not self.is_alive():
            return
        try:
            self.queue.put_nowait(tasks_data)
        except:
            pass

    def collect_and_update(self, env, observations):
        """
        从环境收集数据并更新窗口（便捷方法）

        Args:
            env: Environment 对象
            observations: 环境观察数据
        """
        if not self.is_alive():
            return

        # 收集无人机正在执行的任务
        drone_tasks = []
        for drone in env.drones:
            if drone.executing_task_id:
                drone_tasks.append({
                    'task_id': drone.executing_task_id,
                    'drone_id': drone.drone_id,
                    'priority': 1,
                    'remaining_time': 0,
                    'weight': 0,
                })

        # 计算是否为 peak 阶段
        is_peak = self._calculate_is_peak(env)

        # 组装数据并更新
        self.update({
            'current_time': env.current_time,
            'tasks': observations.get('unassigned_tasks', []),
            'drone_tasks': drone_tasks,
            'completed_count': env.total_completed_tasks,
            'total_tasks': env.total_generated_tasks,
            'free_drones': sum(1 for d in env.drones if d.is_free),
            'busy_drones': sum(1 for d in env.drones if not d.is_free),
            'is_peak': is_peak,
        })

    def _calculate_is_peak(self, env):
        """
        计算当前是否为 peak 阶段

        Returns:
            True: peak 阶段
            False: off-peak 阶段
            None: constant 模式（无 peak 概念）
        """
        task_gen = getattr(env, 'task_generator', None)
        if task_gen is None:
            return None

        # constant 模式没有 peak 概念
        if task_gen.mode != "realistic":
            return None

        # 获取 cycle_length 配置
        from config.config_loder import get_shared_config
        cycle_length = get_shared_config().get("task_generation", {}).get("realistic", {}).get("cycle_length", 500)

        # 计算当前时间在周期中的位置
        cycle_position = env.current_time % cycle_length
        peak_start = cycle_length // 4
        peak_end = peak_start + cycle_length // 4

        return peak_start <= cycle_position < peak_end

    def stop(self):
        """停止任务展示窗口"""
        if self.process is not None and self.process.is_alive():
            try:
                self.queue.put_nowait(None)
                self.process.join(timeout=2)
                if self.process.is_alive():
                    self.process.terminate()
            except:
                pass
        self._running = False
        print("[TaskShower] Task Monitor window closed")

    def is_alive(self):
        """检查窗口进程是否存活"""
        return self.process is not None and self.process.is_alive()


if __name__ == "__main__":
    # Standalone test mode
    print("Task Shower Standalone Test Mode")
    queue = mp.Queue()
    p = mp.Process(target=run_task_shower_process, args=(queue, 0.5), daemon=True)
    p.start()

    # 模拟数据
    import random
    test_data = {
        'current_time': 100,
        'tasks': [
            {'task_id': 'task_1', 'priority': 5, 'remaining_time': 50, 'weight': 2},
            {'task_id': 'task_2', 'priority': 3, 'remaining_time': 100, 'weight': 1},
            {'task_id': 'task_3', 'priority': 1, 'remaining_time': 200, 'weight': 3},
        ],
        'drone_tasks': [
            {'task_id': 'task_0', 'priority': 4, 'remaining_time': 30, 'weight': 2, 'drone_id': 'drone_0'},
        ],
        'completed_count': 5,
        'total_tasks': 10,
        'free_drones': 2,
        'busy_drones': 1,
    }

    for i in range(20):
        queue.put(test_data)
        test_data['current_time'] += 10
        test_data['completed_count'] += 1
        time.sleep(0.5)

    p.join()
