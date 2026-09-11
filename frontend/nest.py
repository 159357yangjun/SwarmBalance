"""机巢（Nest）起降排队调度模块。

解决"地面资源瓶颈"痛点：机巢的起降位（pad）数量有限，多架无人机同时
需要起降时必须排队。排队顺序由**动态优先级仲裁**决定，而非先进先出。

动态优先级三大来源：
1. 降落：电量越低越优先（低于临界电量直接封顶），避免坠机；
2. 起飞：deadline 越近 / 任务优先级越高越优先；
3. 公平：排队等待越久优先级逐步抬升，防止低优先级无人机被无限饿死。

仲裁规则：降落请求永远优先于起飞请求（空中等待的飞机比地面更危险）。
本模块保持零依赖（不 import 项目内部模块），便于独立单元测试。
"""

# ==================== 可调参数 ====================
LANDING_DURATION = 3        # 降落占用 pad 的步数
TAKEOFF_DURATION = 3        # 起飞占用 pad 的步数
CRIT_BATTERY_RATIO = 0.2    # 低于此电量比视为临界返航，降落优先级封顶
URGENCY_HORIZON = 150.0     # 剩余 deadline 小于该值开始计入紧急度
WAIT_SATURATION_STEPS = 50  # 排队等待这么多步后，公平因子达到 1
MAX_QUEUE_WAIT = 60         # 排队超过该步数仍未获准，触发防饥饿硬保底
MAX_TASK_PRIORITY = 3       # 任务优先级上界（用于归一化）

# 正常优先级落在 [0, 1]；防饥饿保底 +1.0 将其抬到 (1, 2]，必然盖过任何未超时请求
STARVATION_BOOST = 1.0

# 优先级权重（三项求和 = 1）
LANDING_WEIGHTS = {"battery": 0.6, "task": 0.2, "wait": 0.2}
TAKEOFF_WEIGHTS = {"deadline": 0.5, "task": 0.3, "wait": 0.2}


def _saturate(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def battery_urgency(battery_ratio):
    """电量紧急度（0~1）：1 表示必须立即降落。

    battery_ratio ∈ [0, 1]。低于 CRIT_BATTERY_RATIO 封顶为 1，
    满电为 0，中间线性过渡。
    """
    if battery_ratio <= CRIT_BATTERY_RATIO:
        return 1.0
    return max(0.0, (1.0 - battery_ratio) / (1.0 - CRIT_BATTERY_RATIO))


def deadline_urgency(remaining_time):
    """截止紧急度（0~1）：1 表示已经超时或必须立即起飞。"""
    if remaining_time is None:
        return 0.0
    if remaining_time <= 0:
        return 1.0
    return max(0.0, 1.0 - remaining_time / URGENCY_HORIZON)


def task_factor(task_priority):
    """任务优先级因子（0~1）：priority 越大越重要。"""
    return _saturate((task_priority - 1) / max(1.0, MAX_TASK_PRIORITY - 1.0))


def wait_factor(wait_steps):
    """等待公平因子（0~1）：等待越久越高，防饥饿。"""
    return _saturate(wait_steps / WAIT_SATURATION_STEPS)


def landing_priority(battery_ratio, task_priority, wait_steps):
    """降落动态优先级（越高越先降落）。

    正常值在 [0, 1]；等待超过 MAX_QUEUE_WAIT 时触发防饥饿保底（>1），
    确保被持续插队的无人机最终也能获准。
    """
    p = (
        LANDING_WEIGHTS["battery"] * battery_urgency(battery_ratio)
        + LANDING_WEIGHTS["task"] * task_factor(task_priority)
        + LANDING_WEIGHTS["wait"] * wait_factor(wait_steps)
    )
    if wait_steps >= MAX_QUEUE_WAIT:
        p += STARVATION_BOOST
    return p


def takeoff_priority(remaining_time, task_priority, wait_steps):
    """起飞动态优先级（越高越先起飞），含防饥饿保底。"""
    p = (
        TAKEOFF_WEIGHTS["deadline"] * deadline_urgency(remaining_time)
        + TAKEOFF_WEIGHTS["task"] * task_factor(task_priority)
        + TAKEOFF_WEIGHTS["wait"] * wait_factor(wait_steps)
    )
    if wait_steps >= MAX_QUEUE_WAIT:
        p += STARVATION_BOOST
    return p


class Pad:
    """单个起降位。"""

    def __init__(self, pad_id):
        self.pad_id = pad_id
        self.busy_until = None   # None 表示空闲，否则为占用至第几 step
        self.drone_id = None
        self.operation = None    # "takeoff" | "landing"

    @property
    def is_free(self):
        return self.busy_until is None


class Nest:
    """机巢：维护起降位与起飞/降落请求队列，每步做动态优先级仲裁。"""

    def __init__(self, nest_id, x, y, num_pads=2,
                 landing_duration=LANDING_DURATION,
                 takeoff_duration=TAKEOFF_DURATION):
        self.nest_id = nest_id
        self.x = x
        self.y = y
        self.landing_duration = landing_duration
        self.takeoff_duration = takeoff_duration
        self.pads = [Pad(i) for i in range(num_pads)]
        self._landing_queue = []   # list of dict: drone_id/battery/task/enqueue_step
        self._takeoff_queue = []

    def get_position(self):
        return (self.x, self.y)

    @property
    def free_pads(self):
        return [p for p in self.pads if p.is_free]

    def request_landing(self, drone_id, battery_ratio, task_priority=1, at_step=0):
        """无人机请求降落（进入降落队列）。"""
        self._landing_queue.append({
            "drone_id": drone_id,
            "battery_ratio": battery_ratio,
            "task_priority": task_priority,
            "enqueue_step": at_step,
        })

    def request_takeoff(self, drone_id, remaining_time, task_priority=1, at_step=0):
        """无人机请求起飞（进入起飞队列）。"""
        self._takeoff_queue.append({
            "drone_id": drone_id,
            "remaining_time": remaining_time,
            "task_priority": task_priority,
            "enqueue_step": at_step,
        })

    def cancel(self, drone_id):
        """无人机离开排队（例如任务被取消）。"""
        self._landing_queue = [r for r in self._landing_queue if r["drone_id"] != drone_id]
        self._takeoff_queue = [r for r in self._takeoff_queue if r["drone_id"] != drone_id]

    def step(self, now):
        """推进一个仿真步：先释放完成起降的 pad，再仲裁新一轮起降。

        返回本步发生的事件列表，每个事件为 dict:
            {"type": "landing_finished"|"takeoff_finished"|"landing_granted"|"takeoff_granted",
             "drone_id", "pad_id", "step"}
        """
        events = []

        # 1. 释放已完成起降的起降位
        for pad in self.pads:
            if pad.busy_until is not None and now >= pad.busy_until:
                events.append({
                    "type": f"{pad.operation}_finished",
                    "drone_id": pad.drone_id,
                    "pad_id": pad.pad_id,
                    "step": now,
                })
                pad.busy_until = None
                pad.drone_id = None
                pad.operation = None

        free = self.free_pads

        # 2. 降落优先仲裁（安全优先）
        if free and self._landing_queue:
            self._sort_landing(now)
            pad = free.pop(0)
            req = self._landing_queue.pop(0)
            self._grant(pad, req["drone_id"], "landing", now)
            events.append({
                "type": "landing_granted",
                "drone_id": req["drone_id"],
                "pad_id": pad.pad_id,
                "step": now,
            })

        # 3. 起飞仲裁（在降落分配之后剩余的 pad 上）
        free = self.free_pads
        if free and self._takeoff_queue:
            self._sort_takeoff(now)
            pad = free.pop(0)
            req = self._takeoff_queue.pop(0)
            self._grant(pad, req["drone_id"], "takeoff", now)
            events.append({
                "type": "takeoff_granted",
                "drone_id": req["drone_id"],
                "pad_id": pad.pad_id,
                "step": now,
            })

        return events

    def _grant(self, pad, drone_id, operation, now):
        pad.drone_id = drone_id
        pad.operation = operation
        pad.busy_until = now + (
            self.landing_duration if operation == "landing" else self.takeoff_duration
        )

    def _sort_landing(self, now):
        self._landing_queue.sort(
            key=lambda r: landing_priority(
                r["battery_ratio"], r["task_priority"], now - r["enqueue_step"]
            ),
            reverse=True,
        )

    def _sort_takeoff(self, now):
        self._takeoff_queue.sort(
            key=lambda r: takeoff_priority(
                r["remaining_time"], r["task_priority"], now - r["enqueue_step"]
            ),
            reverse=True,
        )

    # ==================== 查询接口（供验证/可视化） ====================
    def queue_snapshot(self, now=0):
        self._sort_landing(now)
        self._sort_takeoff(now)
        return {
            "landing": [
                {"drone_id": r["drone_id"],
                 "priority": round(landing_priority(r["battery_ratio"], r["task_priority"], now - r["enqueue_step"]), 4)}
                for r in self._landing_queue
            ],
            "takeoff": [
                {"drone_id": r["drone_id"],
                 "priority": round(takeoff_priority(r["remaining_time"], r["task_priority"], now - r["enqueue_step"]), 4)}
                for r in self._takeoff_queue
            ],
        }

    def pending_landing_ids(self):
        return [r["drone_id"] for r in self._landing_queue]

    def pending_takeoff_ids(self):
        return [r["drone_id"] for r in self._takeoff_queue]