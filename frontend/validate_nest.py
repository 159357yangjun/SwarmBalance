"""机巢起降排队调度的单元验证。

覆盖动态优先级仲裁的核心行为：
- 降落：低电量优先插队
- 起飞：deadline 越近越优先
- 降落永远优先于起飞
- pad 不足时排队等待，释放后继续
- 等待公平因子防饥饿
"""
from nest import (
    Nest, battery_urgency, deadline_urgency, task_factor, wait_factor,
    landing_priority, takeoff_priority, CRIT_BATTERY_RATIO,
)


def check(name, cond):
    assert cond, f"FAILED: {name}"
    print(f"  [OK] {name}")


def test_scalar_functions():
    print("[1] 纯函数边界与单调性")
    # 电量越低紧急度越高
    check("battery 满电为 0", battery_urgency(1.0) == 0.0)
    check("battery 临界封顶 1", battery_urgency(CRIT_BATTERY_RATIO) == 1.0)
    check("battery 低电量 > 高电量", battery_urgency(0.3) > battery_urgency(0.8))
    # deadline 越近越紧急
    check("deadline 超时封顶 1", deadline_urgency(0.0) == 1.0)
    check("deadline 近 > 远", deadline_urgency(30.0) > deadline_urgency(200.0))
    check("deadline None 为 0", deadline_urgency(None) == 0.0)
    # 任务优先级
    check("task p3 > p1", task_factor(3) > task_factor(1))
    # 等待公平
    check("wait 久 > 短", wait_factor(40) > wait_factor(5))
    check("wait 上界 1", wait_factor(1000) == 1.0)


def test_landing_low_battery_first():
    print("[2] 降落：低电量优先")
    nest = Nest("n0", 0, 0, num_pads=1)
    # 满电的先入队，低电量的后入队
    nest.request_landing("d_full", battery_ratio=1.0, at_step=0)
    nest.request_landing("d_low", battery_ratio=0.1, at_step=1)
    events = nest.step(now=1)
    granted = [e for e in events if e["type"] == "landing_granted"]
    check("低电量后入队却先获准", granted and granted[0]["drone_id"] == "d_low")


def test_takeoff_deadline_first():
    print("[3] 起飞：deadline 越近越优先")
    nest = Nest("n0", 0, 0, num_pads=1)
    nest.request_takeoff("d_calm", remaining_time=500.0, at_step=0)
    nest.request_takeoff("d_urgent", remaining_time=10.0, at_step=1)
    events = nest.step(now=1)
    granted = [e for e in events if e["type"] == "takeoff_granted"]
    check("紧急任务后入队却先获准", granted and granted[0]["drone_id"] == "d_urgent")


def test_landing_beats_takeoff():
    print("[4] 降落优先于起飞")
    nest = Nest("n0", 0, 0, num_pads=1)
    nest.request_takeoff("d_takeoff", remaining_time=1.0, task_priority=3, at_step=0)
    nest.request_landing("d_landing", battery_ratio=0.5, at_step=0)
    events = nest.step(now=0)
    types = [e["type"] for e in events]
    check("降落先获准", "landing_granted" in types)
    check("起飞本轮未获准", "takeoff_granted" not in types)


def test_pad_scarcity_queue_and_release():
    print("[5] pad 稀缺：排队 + 释放后继续")
    nest = Nest("n0", 0, 0, num_pads=1)
    nest.request_landing("d1", battery_ratio=0.3, at_step=0)
    nest.request_landing("d2", battery_ratio=0.3, at_step=0)
    nest.step(now=0)  # d1 获准，占用 pad 3 步
    # 第 1 步：pad 仍占用，d2 继续等待
    nest.step(now=1)
    check("d2 仍在排队", "d2" in nest.pending_landing_ids())
    # 逐步推进到 pad 释放（busy_until = 0 + 3 = 3）
    nest.step(now=3)
    check("pad 释放后 d2 获准", "d2" not in nest.pending_landing_ids())


def test_wait_factor_prevents_starvation():
    print("[6] 等待公平因子防饥饿")
    # 高电量（不紧急）的无人机持续排队，等待越久优先级越高，最终不会被饿死
    nest = Nest("n0", 0, 0, num_pads=1)
    nest.request_landing("d_full", battery_ratio=1.0, at_step=0)
    # 每步都有新的低电量无人机插队进来（霸占唯一的 pad）
    got_pad = False
    for now in range(0, 200):
        # 低电量插队者持续出现
        nest.request_landing(f"d_low_{now}", battery_ratio=0.05, at_step=now)
        nest.step(now)
        if "d_full" not in nest.pending_landing_ids():
            got_pad = True
            break
    check("等待足够久后，满电无人机也获准降落", got_pad)


if __name__ == "__main__":
    test_scalar_functions()
    test_landing_low_battery_first()
    test_takeoff_deadline_first()
    test_landing_beats_takeoff()
    test_pad_scarcity_queue_and_release()
    test_wait_factor_prevents_starvation()
    print("\n全部机巢排队调度单元测试通过。")