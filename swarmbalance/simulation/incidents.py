"""Incidents operations on the owning Environment state."""
from __future__ import annotations

def set_drone_out_of_service(environment, drone_id, out_of_service=True, reason='人工故障注入'):
    """运行中将无人机置为停飞/恢复，并在停飞时回收其未完成任务。

    该接口专供交互式仿真事故注入。为了保持现有任务模型简单且可复现，
    故障机上的未完成任务会**回滚到原任务起点**并重新进入待调度池；不会
    在空中创建新的交接点。这样可以直接观察当前调度算法的重新分配过程。
    """
    from swarmbalance.simulation.environment import (os)
    idx = environment._drone_index_by_id(drone_id)
    drone = environment.drones[idx]
    out_of_service = bool(out_of_service)

    if not out_of_service:
        # B5a: once custody was preserved, a simple operational reset
        # cannot pretend an external cargo handoff has happened.
        if getattr(drone, 'cargo_custody_hold_reason', None):
            raise ValueError("[B5A_EXTERNAL_HANDOFF_REQUIRED] cargo still on failed drone")
        if not getattr(drone, 'out_of_service', False):
            return {'drone_idx': idx, 'drone_id': str(drone.drone_id), 'requeued_task_ids': [], 'changed': False}
        drone.out_of_service = False
        drone.out_of_service_reason = None
        drone.is_charging = False
        drone.swap_remaining_steps = 0.0
        drone.charging_station_id = None
        drone.awaiting_berth = False
        drone.berth_station_id = None
        drone.awaiting_since = None
        drone._pending_release = False
        drone._suspended_route = []
        drone._manual_charge_requested = False
        drone.scheduled_position = []
        drone.executing_task_id = None
        drone.current_load = 0.0
        drone.onboard_load_kg = 0.0
        drone.is_free = True
        environment._prev_free_status[idx] = True
        return {'drone_idx': idx, 'drone_id': str(drone.drone_id), 'requeued_task_ids': [], 'changed': True}

    if getattr(drone, 'out_of_service', False):
        return {'drone_idx': idx, 'drone_id': str(drone.drone_id), 'requeued_task_ids': [], 'changed': False}

    # B5a opt-in only: a witnessed source service (load_time) or real
    # onboard mass means this is a custody incident, NOT a fresh order.
    # Keep every assignment on this drone pending an independently audited
    # external handoff; do not requeue even unpicked legs of the same chain
    # while physical cargo is unresolved. Legacy default stays untouched.
    if os.environ.get("SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE") == "1":
        assigned = environment.drone_assignments.get(idx)
        items = (assigned if isinstance(assigned, list)
                 else [assigned] if assigned is not None else [])
        picked = any(isinstance(a, dict) and a.get("load_time") is not None
                     for a in items)
        carrying = float(getattr(drone, "onboard_load_kg", 0.0)) > 1e-9
        if picked or carrying:
            # Reclaim physical nest resources if failure happens during a
            # queue or swap. NEVER award battery energy on a failed swap.
            if (getattr(drone, "is_charging", False)
                    or getattr(drone, "_pending_release", False)):
                st = environment._station_by_id(getattr(drone, "charging_station_id", None))
                if st is not None:
                    st.vacate()
            for q in environment._nest_waiting.values():
                while idx in q:
                    q.remove(idx)
            drone.awaiting_berth = False
            drone.berth_station_id = None
            drone.awaiting_since = None
            drone.is_charging = False
            drone.swap_remaining_steps = 0.0
            drone.charging_station_id = None
            drone._pending_release = False
            drone.out_of_service = True
            drone.out_of_service_reason = str(reason or '人工故障注入')
            drone.cargo_custody_hold_reason = "picked_cargo_requires_external_handoff"
            drone.is_free = False
            environment._prev_free_status[idx] = False
            return {
                'drone_idx': idx, 'drone_id': str(drone.drone_id),
                'requeued_task_ids': [], 'changed': True,
                'cargo_custody_held': True,
                'held_task_ids': [str(a['task'].task_id) for a in items
                                  if isinstance(a, dict) and a.get('task') is not None],
            }

    # 若正在占用换电泊位，故障注入时立即释放，避免机巢资源永久泄漏。
    if getattr(drone, 'is_charging', False):
        st = environment._station_by_id(getattr(drone, 'charging_station_id', None))
        if st is not None:
            st.vacate()
    # 从所有等待队列移除。
    for q in environment._nest_waiting.values():
        while idx in q:
            q.remove(idx)

    requeued = []
    assignments = environment.drone_assignments.pop(idx, None)
    if assignments:
        items = assignments if isinstance(assignments, list) else [assignments]
        existing = {str(t.task_id) for t in environment.task_generator.unassigned_tasks}
        for a in items:
            task = a.get('task') if isinstance(a, dict) else None
            if task is None:
                continue
            tid = str(task.task_id)
            if tid not in existing:
                task.update_status('pending')
                environment.task_generator.unassigned_tasks.append(task)
                existing.add(tid)
                requeued.append(tid)

    drone.scheduled_position = []
    drone._suspended_route = []
    drone._manual_charge_requested = False
    drone.current_load = 0.0
    drone.onboard_load_kg = 0.0
    drone.executing_task_id = None
    drone.is_charging = False
    drone.swap_remaining_steps = 0.0
    drone.charging_station_id = None
    drone.awaiting_berth = False
    drone.berth_station_id = None
    drone.awaiting_since = None
    drone._pending_release = False
    drone.is_free = False
    drone.out_of_service = True
    drone.out_of_service_reason = str(reason or '人工故障注入')
    environment.drone_chain_len[idx] = 0
    environment._prev_free_status[idx] = False
    return {
        'drone_idx': idx,
        'drone_id': str(drone.drone_id),
        'requeued_task_ids': requeued,
        'changed': True,
    }

def set_station_closed(environment, station_id, closed=True, reason='人工场景事件'):
    """运行中关闭/开放机巢。

    关闭采用“软关闭”：不再接收新请求；已经在换电的无人机允许完成。
    原等待队列和正在飞往该机巢的低电无人机会改道到最近的开放机巢。
    为避免场景无任何补能点造成死锁，默认不允许关闭最后一个开放机巢。
    """
    from swarmbalance.simulation.environment import (find_nearest_station, math, os)
    st = environment._station_by_id(station_id)
    if st is None:
        raise ValueError(f"未找到机巢: {station_id}")
    closed = bool(closed)
    if closed == bool(getattr(st, 'closed', False)):
        return {'station_id': str(st.station_id), 'changed': False, 'rerouted_drone_ids': []}

    if closed:
        open_others = [x for x in environment.charging_stations if x is not st and not getattr(x, 'closed', False)]
        if not open_others:
            raise ValueError('至少保留一个开放机巢，不能关闭最后一个可用机巢')
        st.closed = True
        st.closed_reason = str(reason or '人工场景事件')
        rerouted = []
        target_pos = st.get_position()

        # 先处理已经在该站排队的无人机。
        waiting = list(environment._nest_waiting.get(st.station_id, []) or [])
        environment._nest_waiting[st.station_id] = []
        for idx in waiting:
            drone = environment.drones[idx]
            drone.awaiting_berth = False
            drone.berth_station_id = None
            drone.awaiting_since = None
            # Opt-in B3c: no arbitrary move to another nest without
            # quoting its planned map route and validating custody.
            if (os.environ.get("SWARM_BALANCE_CHARGE_TARGET_IDENTITY") == "1"
                    and str(getattr(drone, "charge_target_station_id", "")) == str(st.station_id)):
                drone.charge_target_hold_reason = "target_station_closed"
                continue
            nearest = find_nearest_station(environment.charging_stations, drone.get_position())
            if nearest is not None:
                drone.scheduled_position = [nearest.get_position()]
                drone.is_free = False
                rerouted.append(str(drone.drone_id))

        # 再处理尚未抵达、但正以该站为补能目的地的无人机。
        for drone in environment.drones:
            if getattr(drone, 'out_of_service', False) or getattr(drone, 'is_charging', False):
                continue
            route = list(getattr(drone, 'scheduled_position', []) or [])
            if not route:
                continue
            last = route[-1]
            last_pos = (float(last[0]), float(last[1]))
            headed_for_closed_nest = math.dist(last_pos, target_pos) < 1e-6
            charging_detour = bool(getattr(drone, '_suspended_route', [])) or (getattr(drone, 'executing_task_id', None) is None and not drone.is_free)
            if headed_for_closed_nest and charging_detour:
                if (os.environ.get("SWARM_BALANCE_CHARGE_TARGET_IDENTITY") == "1"
                        and str(getattr(drone, "charge_target_station_id", "")) == str(st.station_id)):
                    drone.charge_target_hold_reason = "target_station_closed"
                    continue
                nearest = find_nearest_station(environment.charging_stations, drone.get_position())
                if nearest is not None:
                    drone.scheduled_position = [nearest.get_position()]
                    drone.is_free = False
                    if str(drone.drone_id) not in rerouted:
                        rerouted.append(str(drone.drone_id))
        return {'station_id': str(st.station_id), 'changed': True, 'rerouted_drone_ids': rerouted}

    st.closed = False
    st.closed_reason = None
    return {'station_id': str(st.station_id), 'changed': True, 'rerouted_drone_ids': []}

def set_task_generation_paused(environment, paused=True):
    """暂停/恢复**自动**任务流；人工注入任务始终允许。"""
    paused = bool(paused)
    changed = paused != bool(getattr(environment, 'task_generation_paused', False))
    environment.task_generation_paused = paused
    return {'paused': paused, 'changed': changed}

def update_pending_task(environment, task_id, *, priority=None, deadline_offset=None,
                        weight=None, category=None):
    """修改仍在待调度池中的任务属性，不影响已经执行中的任务。

    该能力主要用于交互式调度演示：例如把普通订单提升为紧急任务，
    下一步直接观察当前算法是否改变候选机与分配决策。
    """
    from swarmbalance.simulation.environment import (TASK_PRIORITY_MAX, TASK_PRIORITY_MIN)
    task = None
    for item in environment.task_generator.unassigned_tasks:
        if str(item.task_id) == str(task_id):
            task = item
            break
    if task is None:
        raise ValueError(f"任务 {task_id} 不在待调度池中，只有待调度任务可以修改")

    changed = {}
    if priority is not None:
        p = max(TASK_PRIORITY_MIN, min(TASK_PRIORITY_MAX, int(priority)))
        if p != int(task.priority):
            changed['priority'] = [int(task.priority), p]
            task.priority = p
    if deadline_offset is not None:
        off = float(deadline_offset)
        if off <= 0:
            raise ValueError("距截止时间必须大于 0 秒")
        old = float(task.deadline) if task.deadline is not None else None
        task.deadline = float(environment.current_time) + off
        changed['deadline'] = [old, float(task.deadline)]
    if weight is not None:
        w = float(weight)
        if w <= 0:
            raise ValueError("任务重量必须大于 0")
        max_capacity = max((float(getattr(d, 'carrying_capacity', 0.0)) for d in environment.drones), default=0.0)
        if max_capacity > 0 and w > max_capacity + 1e-9:
            raise ValueError(f"任务重量 {w:g}kg 超过当前机队最大载重 {max_capacity:g}kg")
        if abs(w - float(task.weight)) > 1e-9:
            changed['weight'] = [float(task.weight), w]
            task.weight = w
    if category is not None:
        c = str(category or 'normal').strip().lower()
        if c not in {'normal', 'urgent', 'emergency', 'bulk'}:
            raise ValueError(f"未知任务类别: {category}")
        if c != str(task.category):
            changed['category'] = [str(task.category), c]
            task.category = c
    return {'task_id': str(task.task_id), 'changed': changed}

def resume_held_charge_route(environment, drone_id):
    """B4c experimental explicit resume, after a fresh A* and Wh quote.

    Reopening a nest does NOT release a prior hold. The operator must
    explicitly request resumption, and *all* checks happen before any
    battery, position, mission or route mutation. This API does not
    create external rescue, cargo transfer or recharge events.
    """
    from swarmbalance.simulation.environment import (os)
    if (os.environ.get("SWARM_BALANCE_HELD_ROUTE_REQUOTE") != "1"
            or os.environ.get("SWARM_BALANCE_AUTO_PLANNED_STATION") != "1"
            or os.environ.get("SWARM_BALANCE_CHARGE_TARGET_IDENTITY") != "1"):
        raise ValueError("[B4C_OPT_IN_REQUIRED] all route and identity gates must be enabled")
    idx = environment._drone_index_by_id(drone_id)
    drone = environment.drones[idx]
    if (getattr(drone, "out_of_service", False)
            or getattr(drone, "is_charging", False)
            or getattr(drone, "awaiting_berth", False)
            or getattr(drone, "_manual_charge_requested", False)
            or not getattr(drone, "_suspended_route", [])
            or not getattr(drone, "charge_target_hold_reason", None)):
        raise ValueError("[B4C_NOT_HELD_AUTO_CHARGE] no supported recovery state")
    target_id = getattr(drone, "charge_target_station_id", None)
    target = environment._station_by_id(target_id)
    if target is None or getattr(target, "closed", False):
        raise ValueError("[B4C_STATION_CLOSED] requested target is absent or closed")
    # This quote uses real current position, current wind and B1 single
    # source Wh. It fails closed on planner fallback and missing reserve.
    fresh = environment.quote_planned_station_energy_wh(drone, target)
    if (not fresh["feasible"] or fresh["fallback"]
            or not fresh["affordable"]):
        raise ValueError("[B4C_ROUTE_UNAFFORDABLE] %s" % fresh["reason"])
    new_waypoints = [(float(x), float(y), "waypoint")
                     for x, y in fresh["waypoints"]]
    if not new_waypoints and drone.get_position() != target.get_position():
        raise ValueError("[B4C_NO_PLANNED_WAYPOINTS] unexpected empty route")
    # Atomic state transition after all eligibility and Wh checks.
    drone.scheduled_position = new_waypoints
    drone.charge_target_hold_reason = None
    drone.flight_energy_blocked = False
    drone.flight_energy_block_reason = None
    drone.is_free = False
    environment._prev_free_status[idx] = False
    if not new_waypoints:
        drone.awaiting_berth = True
        drone.berth_station_id = target.station_id
        drone.awaiting_since = float(environment.current_time)
    return {
        "drone_id": str(drone.drone_id),
        "station_id": str(target.station_id),
        "changed": True,
        "planned_distance_m": fresh["distance_m"],
        "required_wh": fresh["required_wh"],
        "reserve_wh": fresh["reserve_wh"],
    }

def request_drone_charge(environment, drone_id, station_id=None):
    """人工请求无人机前往指定/最近开放机巢换电。

    正在执行任务时会挂起剩余航线，换电完成后恢复；空闲机则单纯前往机巢
    换电。全过程仍走有限泊位与动态优先级仲裁，不绕过资源约束。
    """
    from swarmbalance.simulation.environment import (find_nearest_station, math, os)
    idx = environment._drone_index_by_id(drone_id)
    drone = environment.drones[idx]
    if getattr(drone, 'out_of_service', False):
        raise ValueError(f"{drone.drone_id} 当前故障停飞，不能调往机巢")
    if getattr(drone, 'is_charging', False):
        return {'drone_id': str(drone.drone_id), 'station_id': str(drone.charging_station_id), 'changed': False, 'reason': 'already_charging'}
    if getattr(drone, 'awaiting_berth', False):
        return {'drone_id': str(drone.drone_id), 'station_id': str(drone.berth_station_id), 'changed': False, 'reason': 'already_waiting'}

    if station_id is None:
        st = find_nearest_station(environment.charging_stations, drone.get_position())
    else:
        st = environment._station_by_id(station_id)
        if st is not None and getattr(st, 'closed', False):
            raise ValueError(f"机巢 {station_id} 当前关闭")
    if st is None:
        raise ValueError("当前没有可用机巢")

    # B3b experimental ONLY. Produce a real obstacle-aware route and a
    # complete per-leg B1 Wh quote BEFORE changing mission/cargo/berth.
    # Default-off leaves legacy direct-hop behavior byte-for-byte intact.
    planned_charge_waypoints = None
    if os.environ.get("SWARM_BALANCE_PLANNED_STATION_ROUTE") == "1":
        already_at_nest = math.dist(drone.get_position(), st.get_position()) < 1e-6
        if not already_at_nest:
            planned_quote = environment.quote_planned_station_energy_wh(drone, st)
            if not planned_quote["feasible"] or not planned_quote["affordable"]:
                raise ValueError(
                    "[B3B_NO_AFFORDABLE_PLANNED_ROUTE] station=%s reason=%s" %
                    (st.station_id, planned_quote["reason"]))
            # Tag ALL diversion legs as non-service; never consume
            # source/dest while travelling to a charging nest.
            planned_charge_waypoints = [
                (float(x), float(y), "waypoint")
                for x, y in planned_quote["waypoints"]
            ]

    # B3c: record requested charging *identity* separately from nearest
    # geometry, only under explicit opt-in. A failed quote above must
    # leave all mission and target state untouched.
    if os.environ.get("SWARM_BALANCE_CHARGE_TARGET_IDENTITY") == "1":
        drone.charge_target_station_id = st.station_id
        drone.charge_target_hold_reason = None
    route = list(getattr(drone, 'scheduled_position', []) or [])
    if route and not getattr(drone, '_suspended_route', []):
        drone._suspended_route = route
    drone._manual_charge_requested = True
    target = st.get_position()
    if math.dist(drone.get_position(), target) < 1e-6:
        drone.scheduled_position = []
        drone.awaiting_berth = True
        drone.berth_station_id = st.station_id
        drone.awaiting_since = float(environment.current_time)
        drone.is_free = False
    else:
        drone.scheduled_position = (planned_charge_waypoints
                                    if planned_charge_waypoints is not None
                                    else [target])
        drone.is_free = False
    environment._prev_free_status[idx] = False
    return {
        'drone_id': str(drone.drone_id),
        'station_id': str(st.station_id),
        'changed': True,
        'resume_tasks_after_charge': bool(getattr(drone, '_suspended_route', [])),
    }
