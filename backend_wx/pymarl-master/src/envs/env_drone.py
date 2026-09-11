import os
import sys
from pathlib import Path

import numpy as np

from .multiagentenv import MultiAgentEnv


class EnvDroneEnv(MultiAgentEnv):
    """PyMARL env wrapper for direct Python integration with frontend Environment."""

    def __init__(
        self,
        episode_limit=None,
        max_tasks=None,
        frontend_root=None,
        map_relative_path=None,
        seed=None,
        **kwargs,
    ):
        del kwargs

        self._project_root = self._resolve_project_root(frontend_root)
        shared_cfg = self._load_shared_config()
        env_cfg = shared_cfg.get("environment", {})
        task_cfg = shared_cfg.get("task", {})

        if episode_limit is None:
            episode_limit = env_cfg.get("episode_max_steps", 1200)
        if max_tasks is None:
            max_tasks = env_cfg.get("max_obs_tasks", 5)
        if map_relative_path is None:
            map_relative_path = env_cfg.get("map_relative_path", "data/map/part_of_yangpu.osm")

        self.episode_limit = int(episode_limit)
        self.max_tasks = int(max_tasks)
        self._max_remaining_time = float(task_cfg.get("deadline_offset_max", 600.0))
        if self._max_remaining_time <= 0:
            self._max_remaining_time = 1.0
        self._priority_max = float(task_cfg.get("priority_max", 3.0))
        self._warehouse_pos = task_cfg.get("warehouse_pos", [0.0, 0.0])
        self._max_weight = float(task_cfg.get("weight_max", 10.0))
        self._episode_seed = None

        self._frontend_dir = self._project_root / "frontend"
        self._map_path = self._frontend_dir / map_relative_path

        self._prepare_frontend_import_paths()
        self._frontend_env = self._create_frontend_env()

        self.n_agents = len(self._frontend_env.drones)
        self.n_actions = self.max_tasks + 1  # action 0 is NoOp
        self.noop_action = 0

        self._task_feature_dim = 10
        self._agent_feature_dim = 5
        self._obs_size = self._agent_feature_dim + self.max_tasks * self._task_feature_dim
        self._state_size = self.n_agents * self._agent_feature_dim + self.max_tasks * self._task_feature_dim

        self._bounds = self._frontend_env.get_global_bounds()
        self._max_dist = self._estimate_max_distance(self._bounds)
        self._reward_cfg = shared_cfg.get("qmix_reward", {})
        self._reward_completion_bonus = float(self._reward_cfg.get("completion_bonus", 1.0))
        self._reward_backlog_penalty = float(self._reward_cfg.get("backlog_penalty", 0.0))
        self._reward_invalid_action_penalty = float(self._reward_cfg.get("invalid_action_penalty", 0.0))
        self._reward_overdue_step_penalty = float(self._reward_cfg.get("overdue_step_penalty", 0.0))
        self._reward_idle_penalty = float(self._reward_cfg.get("idle_penalty", 0.0))
        self._reward_uncompleted_penalty = float(self._reward_cfg.get("uncompleted_penalty", 0.0))
        self._reward_completion_rate_bonus = float(self._reward_cfg.get("completion_rate_bonus", 0.0))
        self._reward_priority_delay_weights = {
            1: float(self._reward_cfg.get("priority_delay_weight_1", 1.0)),
            2: float(self._reward_cfg.get("priority_delay_weight_2", 1.5)),
            3: float(self._reward_cfg.get("priority_delay_weight_3", 2.0)),
        }
        self._reward_urgency_backlog_base = float(self._reward_cfg.get("urgency_backlog_base", 0.25))
        self._reward_overdue_severity_scale = float(self._reward_cfg.get("overdue_severity_scale", 100.0))
        self._reward_terminal_delay_penalty = float(self._reward_cfg.get("terminal_delay_penalty", 0.0))
        self._reward_scale = float(self._reward_cfg.get("reward_scale", 1.0))
        self._reward_clip = self._reward_cfg.get("reward_clip", None)
        if self._reward_clip is not None:
            self._reward_clip = abs(float(self._reward_clip))
        repair_cfg = shared_cfg.get("qmix_assignment_repair", {})
        self._repair_assignments = bool(repair_cfg.get("enabled", True))
        self._repair_priority_weight = float(repair_cfg.get("priority_weight", 2.0))
        self._repair_urgency_weight = float(repair_cfg.get("urgency_weight", 5.0))
        self._repair_source_distance_weight = float(repair_cfg.get("source_distance_weight", 1.5))
        self._repair_route_distance_weight = float(repair_cfg.get("route_distance_weight", 0.5))
        self._t = 0
        self._last_obs = None
        self._prev_completed = 0
        self.reset()

    @staticmethod
    def _is_padded_task(task):
        if not isinstance(task, dict):
            return True
        task_id = task.get("task_id")
        if isinstance(task_id, str) and task_id.startswith("__pad_"):
            return True
        return task_id is None

    def _resolve_project_root(self, frontend_root):
        if frontend_root:
            root = Path(frontend_root).resolve()
        else:
            root = Path(__file__).resolve().parents[4]
        if not (root / "frontend").exists():
            raise FileNotFoundError("Cannot find frontend directory under project root.")
        return root

    @staticmethod
    def _estimate_max_distance(bounds):
        if not bounds:
            return 1.0
        min_x, min_y, max_x, max_y = bounds
        dx = max_x - min_x
        dy = max_y - min_y
        return max((dx ** 2 + dy ** 2) ** 0.5, 1.0)

    def _load_shared_config(self):
        cfg_path = self._project_root / "config" / "simulation.json"
        if not cfg_path.exists():
            return {}

        root_dir_str = str(self._project_root)
        if root_dir_str not in sys.path:
            sys.path.insert(0, root_dir_str)

        from config.config_loder import get_shared_config

        shared_cfg = get_shared_config(str(cfg_path))
        task_gen = shared_cfg.get("task_generation")
        if isinstance(task_gen, dict):
            task_gen["mode"] = "realistic"
        return shared_cfg

    def _prepare_frontend_import_paths(self):
        frontend_dir_str = str(self._frontend_dir)
        root_dir_str = str(self._project_root)
        if frontend_dir_str not in sys.path:
            sys.path.insert(0, frontend_dir_str)
        if root_dir_str not in sys.path:
            sys.path.insert(0, root_dir_str)

    def _create_frontend_env(self):
        prev_cwd = os.getcwd()
        try:
            # frontend Environment relies on relative paths for local assets.
            os.chdir(str(self._frontend_dir))
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            try:
                from environment import Environment
            except ModuleNotFoundError as exc:
                message = (
                    "Failed to import frontend.environment. "
                    "Ensure frontend directory is on sys.path and current working directory is the frontend root."
                )
                raise ModuleNotFoundError(message) from exc
            return Environment(str(self._map_path), visualize=False, episode_max_steps=self.episode_limit)
        finally:
            os.chdir(prev_cwd)

    def set_episode_seed(self, seed):
        if seed is None:
            self._episode_seed = None
        else:
            self._episode_seed = int(seed)

    def reset(self):
        self._t = 0
        if self._episode_seed is not None:
            try:
                self._last_obs = self._frontend_env.reset(seed=self._episode_seed)
            except TypeError:
                if hasattr(self._frontend_env, "set_seed"):
                    self._frontend_env.set_seed(self._episode_seed)
                self._last_obs = self._frontend_env.reset()
        else:
            self._last_obs = self._frontend_env.reset()
        self._prev_completed = 0
        return self.get_obs(), self.get_state()

    def step(self, actions):
        action_list = self._to_action_list(actions)
        obs_before = self._last_obs if self._last_obs is not None else self._frontend_env._obs()

        assignments = {}
        unassigned_tasks = obs_before.get("unassigned_tasks", [])
        drone_is_free = obs_before.get("drone_is_free", [True] * self.n_agents)
        drone_free_masks = obs_before.get("drone_free_masks", [])
        drone_positions = obs_before.get("drone_positions", [[0.0, 0.0]] * self.n_agents)
        invalid_actions = 0
        idle_actions = 0
        used_task_ids = set()

        for agent_id, action in enumerate(action_list):
            if action <= 0:
                if agent_id < len(drone_is_free) and drone_is_free[agent_id]:
                    idle_actions += 1
                continue
            task_slot = action - 1
            if task_slot >= len(unassigned_tasks):
                invalid_actions += 1
                continue
            if not self._agent_can_take_action(agent_id, task_slot, drone_is_free, drone_free_masks):
                invalid_actions += 1
                continue

            task_dict = unassigned_tasks[task_slot]
            if self._is_padded_task(task_dict):
                invalid_actions += 1
                continue

            task_id = task_dict.get("task_id")
            if task_id is None:
                invalid_actions += 1
                continue
            if task_id in used_task_ids:
                invalid_actions += 1
                continue
            assignments[agent_id] = [task_id]
            used_task_ids.add(task_id)

        repaired_actions = 0
        if self._repair_assignments:
            repaired_actions = self._repair_idle_assignments(
                assignments,
                used_task_ids,
                obs_before,
            )

        next_obs, reward, frontend_done, frontend_info = self._frontend_env.step(assignments)
        self._last_obs = next_obs
        self._t += 1

        stats = self._frontend_env.get_statistics() if hasattr(self._frontend_env, "get_statistics") else {}
        total_completed = int(stats.get("total_completed", 0))
        completion_delta = total_completed - self._prev_completed
        self._prev_completed = total_completed
        unassigned_cost = self._weighted_backlog_cost(next_obs.get("unassigned_tasks", []))
        overdue_cost = self._weighted_overdue_cost(next_obs.get("unassigned_tasks", []))

        shaped = (
            self._reward_completion_bonus * completion_delta
            - self._reward_backlog_penalty * unassigned_cost
            - self._reward_invalid_action_penalty * invalid_actions
            - self._reward_overdue_step_penalty * overdue_cost
            - self._reward_idle_penalty * idle_actions
        )
        reward = float(reward) + float(shaped)

        hit_episode_limit = self._t >= self.episode_limit
        terminated = bool(hit_episode_limit or frontend_done)
        env_info = {
            "episode_limit": bool(hit_episode_limit),
            "invalid_actions": int(invalid_actions),
            "idle_actions": int(idle_actions),
            "repaired_actions": int(repaired_actions),
        }

        if terminated:
            total_generated = int(stats.get("total_generated", 0))
            remaining = max(0, total_generated - total_completed)
            completion_rate = (
                total_completed / total_generated
                if total_generated > 0 else 0.0
            )
            reward = float(reward) + float(self._reward_completion_rate_bonus * (completion_rate ** 2))
            if self._reward_terminal_delay_penalty > 0 and hasattr(self._frontend_env, "get_statistics"):
                delay_cost = self._terminal_priority_delay_cost(stats)
                reward = float(reward) - float(self._reward_terminal_delay_penalty * delay_cost)
            if remaining > 0:
                reward = float(reward) - float(self._reward_uncompleted_penalty * remaining)
            if isinstance(frontend_info, dict):
                for k in (
                    "completion_rate",
                    "on_time_rate",
                    "timeout_rate",
                    "avg_delay",
                    "avg_generation_to_assignment_wait",
                    "avg_assignment_to_load_wait",
                    "avg_wait_time_to_load",
                    "avg_load_to_delivery_time",
                    "avg_delivery_time",
                    "avg_generation_to_completion_time",
                    "avg_generation_time",
                    "total_completed",
                    "total_generated",
                    "avg_steps_per_order",
                    "total_energy_consumed",
                    "avg_energy_per_task",
                    "max_delivery_time",
                    "max_generation_to_completion_time",
                    "avg_delay_priority_1",
                    "avg_delay_priority_2",
                    "avg_delay_priority_3",
                ):
                    if k in frontend_info:
                        if k == "total_completed":
                            env_info[k] = int(frontend_info[k])
                        elif k == "total_generated":
                            env_info[k] = int(frontend_info[k])
                        else:
                            env_info[k] = float(frontend_info[k])
            if hasattr(self._frontend_env, "get_statistics"):
                stats = self._frontend_env.get_statistics()
                env_info["completion_rate"] = float(stats.get("completion_rate", env_info.get("completion_rate", 0.0)))
                env_info["on_time_rate"] = float(stats.get("on_time_rate", env_info.get("on_time_rate", 0.0)))
                env_info["timeout_rate"] = float(stats.get("timeout_rate", env_info.get("timeout_rate", 0.0)))
                env_info["avg_delay"] = float(stats.get("avg_delay", env_info.get("avg_delay", 0.0)))
                env_info["total_completed"] = int(stats.get("total_completed", env_info.get("total_completed", 0)))
                env_info["total_generated"] = int(stats.get("total_generated", env_info.get("total_generated", 0)))
                env_info["avg_generation_to_assignment_wait"] = float(
                    stats.get("avg_generation_to_assignment_wait", env_info.get("avg_generation_to_assignment_wait", 0.0))
                )
                env_info["avg_assignment_to_load_wait"] = float(
                    stats.get("avg_assignment_to_load_wait", env_info.get("avg_assignment_to_load_wait", 0.0))
                )
                env_info["avg_wait_time_to_load"] = float(
                    stats.get("avg_wait_time_to_load", env_info.get("avg_wait_time_to_load", 0.0))
                )
                env_info["avg_load_to_delivery_time"] = float(
                    stats.get("avg_load_to_delivery_time", env_info.get("avg_load_to_delivery_time", 0.0))
                )
                env_info["avg_delivery_time"] = float(
                    stats.get("avg_delivery_time", env_info.get("avg_delivery_time", 0.0))
                )
                env_info["avg_generation_to_completion_time"] = float(
                    stats.get("avg_generation_to_completion_time", env_info.get("avg_generation_to_completion_time", 0.0))
                )
                env_info["avg_generation_time"] = float(
                    stats.get("avg_generation_time", env_info.get("avg_generation_time", 0.0))
                )
                env_info["avg_steps_per_order"] = float(
                    stats.get("avg_steps_per_order", env_info.get("avg_steps_per_order", 0.0))
                )
                env_info["total_energy_consumed"] = float(stats.get("total_energy_consumed", env_info.get("total_energy_consumed", 0.0)))
                env_info["avg_energy_per_task"] = float(stats.get("avg_energy_per_task", env_info.get("avg_energy_per_task", 0.0)))
                env_info["avg_energy_per_distance"] = float(stats.get("avg_energy_per_distance", env_info.get("avg_energy_per_distance", 0.0)))
                env_info["max_delivery_time"] = float(stats.get("max_delivery_time", env_info.get("max_delivery_time", 0.0)))
                env_info["max_generation_to_completion_time"] = float(
                    stats.get("max_generation_to_completion_time", env_info.get("max_generation_to_completion_time", 0.0))
                )
                env_info["avg_delay_priority_1"] = float(stats.get("avg_delay_priority_1", env_info.get("avg_delay_priority_1", 0.0)))
                env_info["avg_delay_priority_2"] = float(stats.get("avg_delay_priority_2", env_info.get("avg_delay_priority_2", 0.0)))
                env_info["avg_delay_priority_3"] = float(stats.get("avg_delay_priority_3", env_info.get("avg_delay_priority_3", 0.0)))

        reward = float(reward) * self._reward_scale
        if self._reward_clip is not None:
            reward = float(np.clip(reward, -self._reward_clip, self._reward_clip))

        return float(reward), terminated, env_info

    def _to_action_list(self, actions):
        if hasattr(actions, "detach"):
            arr = actions.detach().cpu().numpy()
        else:
            arr = np.asarray(actions)
        arr = np.array(arr).reshape(-1)
        out = []
        for i in range(self.n_agents):
            if i < arr.shape[0]:
                out.append(int(arr[i]))
            else:
                out.append(0)
        return out

    def _norm_coord(self, x, y):
        if not self._bounds:
            return 0.0, 0.0
        min_x, min_y, max_x, max_y = self._bounds
        dx = max(max_x - min_x, 1e-6)
        dy = max(max_y - min_y, 1e-6)
        nx = float((x - min_x) / dx)
        ny = float((y - min_y) / dy)
        return nx, ny

    def _count_unassigned(self, tasks):
        return sum(0 if self._is_padded_task(t) else 1 for t in tasks)

    def _count_overdue(self, tasks):
        overdue = 0
        for task in tasks:
            if self._is_padded_task(task):
                continue
            remaining = task.get("remaining_time", 0)
            try:
                if float(remaining) < 0:
                    overdue += 1
            except (TypeError, ValueError):
                continue
        return overdue

    def _priority_delay_weight(self, priority):
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = 1
        return self._reward_priority_delay_weights.get(priority, self._reward_priority_delay_weights[1])

    def _weighted_backlog_cost(self, tasks):
        cost = 0.0
        for task in tasks:
            if self._is_padded_task(task):
                continue
            remaining = task.get("remaining_time", self._max_remaining_time)
            try:
                remaining = float(remaining)
            except (TypeError, ValueError):
                remaining = self._max_remaining_time
            urgency = 1.0 - float(np.clip(remaining / max(self._max_remaining_time, 1.0), 0.0, 1.0))
            if remaining < 0:
                urgency = 1.0
            priority_weight = self._priority_delay_weight(task.get("priority", 1))
            cost += priority_weight * (self._reward_urgency_backlog_base + urgency)
        return cost

    def _weighted_overdue_cost(self, tasks):
        cost = 0.0
        for task in tasks:
            if self._is_padded_task(task):
                continue
            remaining = task.get("remaining_time", 0)
            try:
                remaining = float(remaining)
            except (TypeError, ValueError):
                continue
            if remaining >= 0:
                continue
            priority_weight = self._priority_delay_weight(task.get("priority", 1))
            severity = 1.0 + min(abs(remaining) / max(self._reward_overdue_severity_scale, 1.0), 3.0)
            cost += priority_weight * severity
        return cost

    def _terminal_priority_delay_cost(self, stats):
        weighted_delay = 0.0
        total_weight = 0.0
        for priority in (1, 2, 3):
            weight = self._priority_delay_weight(priority)
            delay = float(stats.get(f"avg_delay_priority_{priority}", 0.0))
            weighted_delay += weight * delay
            total_weight += weight
        return weighted_delay / max(total_weight, 1.0)

    def _agent_can_take_action(self, agent_id, task_slot, drone_is_free, drone_free_masks):
        if agent_id < len(drone_is_free) and drone_is_free[agent_id]:
            return True
        if agent_id < len(drone_free_masks):
            mask = drone_free_masks[agent_id]
            if task_slot < len(mask):
                return bool(mask[task_slot])
        return False

    def _repair_idle_assignments(self, assignments, used_task_ids, observation):
        tasks = observation.get("unassigned_tasks", [])
        drone_is_free = observation.get("drone_is_free", [True] * self.n_agents)
        drone_free_masks = observation.get("drone_free_masks", [])
        drone_positions = observation.get("drone_positions", [[0.0, 0.0]] * self.n_agents)
        remaining_tasks = [
            task for task in tasks
            if not self._is_padded_task(task) and task.get("task_id") not in used_task_ids
        ]
        if not remaining_tasks:
            return 0

        repaired = 0

        try:
            from greedy.scheduler import greedy_action_from_observation
            greedy_assignments = greedy_action_from_observation(observation)
        except Exception:
            greedy_assignments = {}

        task_ids_available = {task.get("task_id") for task in remaining_tasks}
        task_slots = {task.get("task_id"): slot for slot, task in enumerate(tasks)}
        for agent_id, task_ids in greedy_assignments.items():
            if agent_id in assignments:
                continue
            for task_id in task_ids:
                if task_id not in task_ids_available or task_id in used_task_ids:
                    continue
                task_slot = task_slots.get(task_id)
                if task_slot is None or not self._agent_can_take_action(agent_id, task_slot, drone_is_free, drone_free_masks):
                    continue
                assignments[agent_id] = [task_id]
                used_task_ids.add(task_id)
                remaining_tasks = [task for task in remaining_tasks if task.get("task_id") != task_id]
                task_ids_available.remove(task_id)
                repaired += 1
                break

        for agent_id in range(self.n_agents):
            if agent_id in assignments:
                continue
            if not remaining_tasks:
                break

            drone_pos = drone_positions[agent_id] if agent_id < len(drone_positions) else [0.0, 0.0]
            valid_tasks = [
                task for task in remaining_tasks
                if self._agent_can_take_action(
                    agent_id,
                    task_slots.get(task.get("task_id"), self.max_tasks),
                    drone_is_free,
                    drone_free_masks,
                )
            ]
            if not valid_tasks:
                continue
            best_task = max(valid_tasks, key=lambda task: self._repair_task_score(task, drone_pos))
            task_id = best_task.get("task_id")
            if task_id is None:
                continue
            assignments[agent_id] = [task_id]
            used_task_ids.add(task_id)
            remaining_tasks.remove(best_task)
            repaired += 1
        return repaired

    def _repair_task_score(self, task, drone_pos):
        remaining = task.get("remaining_time", self._max_remaining_time)
        try:
            remaining = float(remaining)
        except (TypeError, ValueError):
            remaining = self._max_remaining_time
        urgency = 1.0 - float(np.clip(remaining / max(self._max_remaining_time, 1.0), 0.0, 1.0))

        priority_max = self._priority_max if self._priority_max > 0 else 1.0
        priority = float(task.get("priority", 0.0)) / priority_max

        source = task.get("source", [0.0, 0.0])
        try:
            source_distance = float(((float(source[0]) - float(drone_pos[0])) ** 2 + (float(source[1]) - float(drone_pos[1])) ** 2) ** 0.5)
        except (TypeError, ValueError, IndexError):
            source_distance = self._max_dist
        source_distance = source_distance / max(self._max_dist, 1.0)

        route_distance = task.get("route_distance")
        if route_distance is None:
            dest = task.get("destination", [0.0, 0.0])
            try:
                route_distance = float(((float(source[0]) - float(dest[0])) ** 2 + (float(source[1]) - float(dest[1])) ** 2) ** 0.5)
            except (TypeError, ValueError, IndexError):
                route_distance = self._max_dist
        route_distance = float(route_distance) / max(self._max_dist, 1.0)

        return (
            self._repair_urgency_weight * urgency
            + self._repair_priority_weight * priority
            - self._repair_source_distance_weight * source_distance
            - self._repair_route_distance_weight * route_distance
        )

    def _task_vector(self, task):
        if self._is_padded_task(task):
            return [0.0] * self._task_feature_dim
        sx, sy = task.get("source", [0.0, 0.0])
        dx, dy = task.get("destination", [0.0, 0.0])
        nsx, nsy = self._norm_coord(sx, sy)
        ndx, ndy = self._norm_coord(dx, dy)

        rem = task.get("remaining_time", self._max_remaining_time)
        if np.isinf(rem):
            rem = self._max_remaining_time
        rem = float(np.clip(rem / max(self._max_remaining_time, 1.0), 0.0, 1.0))

        priority_max = self._priority_max if self._priority_max > 0 else 1.0
        priority = float(task.get("priority", 0.0)) / priority_max
        weight_den = self._max_weight if self._max_weight > 0 else 1.0
        weight = float(task.get("weight", 0.0)) / weight_den
        route_distance = task.get("route_distance")
        if route_distance is None:
            route_distance = float(((sx - dx) ** 2 + (sy - dy) ** 2) ** 0.5)
        route_distance = float(route_distance) / self._max_dist
        source_to_warehouse = task.get("source_to_warehouse")
        if source_to_warehouse is None:
            wx, wy = self._warehouse_pos
            source_to_warehouse = float(((sx - wx) ** 2 + (sy - wy) ** 2) ** 0.5)
        source_to_warehouse = float(source_to_warehouse) / self._max_dist
        active = 1.0
        return [nsx, nsy, ndx, ndy, rem, priority, weight, route_distance, source_to_warehouse, active]

    def _flatten_tasks(self):
        task_features = []
        tasks = [] if self._last_obs is None else self._last_obs.get("unassigned_tasks", [])
        for i in range(self.max_tasks):
            if i < len(tasks):
                task_features.extend(self._task_vector(tasks[i]))
            else:
                task_features.extend([0.0] * self._task_feature_dim)
        return task_features

    def get_obs(self):
        if self._last_obs is None:
            return [[0.0] * self._obs_size for _ in range(self.n_agents)]

        tasks_flat = self._flatten_tasks()
        drone_positions = self._last_obs.get("drone_positions", [[0.0, 0.0]] * self.n_agents)
        drone_is_free = self._last_obs.get("drone_is_free", [True] * self.n_agents)
        drone_batteries = self._last_obs.get("drone_batteries", [])
        drone_loads = self._last_obs.get("drone_loads", [])

        obs = []
        for agent_id in range(self.n_agents):
            x, y = drone_positions[agent_id]
            nx, ny = self._norm_coord(x, y)
            is_free = 1.0 if drone_is_free[agent_id] else 0.0
            battery_ratio = 0.0
            if agent_id < len(drone_batteries):
                cap = float(drone_batteries[agent_id].get("capacity", 1.0))
                cur = float(drone_batteries[agent_id].get("current", 0.0))
                if cap > 0:
                    battery_ratio = cur / cap
            load_ratio = 0.0
            if agent_id < len(drone_loads):
                cap = float(drone_loads[agent_id].get("capacity", 1.0))
                cur = float(drone_loads[agent_id].get("current", 0.0))
                if cap > 0:
                    load_ratio = cur / cap
            obs.append([nx, ny, is_free, battery_ratio, load_ratio] + tasks_flat)
        return obs

    def get_obs_agent(self, agent_id):
        return self.get_obs()[agent_id]

    def get_obs_size(self):
        return self._obs_size

    def get_state(self):
        if self._last_obs is None:
            return [0.0] * self._state_size

        state = []
        drone_positions = self._last_obs.get("drone_positions", [[0.0, 0.0]] * self.n_agents)
        drone_is_free = self._last_obs.get("drone_is_free", [True] * self.n_agents)
        drone_batteries = self._last_obs.get("drone_batteries", [])
        drone_loads = self._last_obs.get("drone_loads", [])

        for agent_id in range(self.n_agents):
            x, y = drone_positions[agent_id]
            nx, ny = self._norm_coord(x, y)
            is_free = 1.0 if drone_is_free[agent_id] else 0.0
            battery_ratio = 0.0
            if agent_id < len(drone_batteries):
                cap = float(drone_batteries[agent_id].get("capacity", 1.0))
                cur = float(drone_batteries[agent_id].get("current", 0.0))
                if cap > 0:
                    battery_ratio = cur / cap
            load_ratio = 0.0
            if agent_id < len(drone_loads):
                cap = float(drone_loads[agent_id].get("capacity", 1.0))
                cur = float(drone_loads[agent_id].get("current", 0.0))
                if cap > 0:
                    load_ratio = cur / cap
            state.extend([nx, ny, is_free, battery_ratio, load_ratio])

        state.extend(self._flatten_tasks())
        return state

    def get_state_size(self):
        return self._state_size

    def get_avail_actions(self):
        return [self.get_avail_agent_actions(agent_id) for agent_id in range(self.n_agents)]

    def get_avail_agent_actions(self, agent_id):
        avail = [0] * self.n_actions
        avail[self.noop_action] = 1

        if self._last_obs is None:
            return avail

        tasks = self._last_obs.get("unassigned_tasks", [])
        drone_is_free = self._last_obs.get("drone_is_free", [True] * self.n_agents)
        drone_free_masks = self._last_obs.get("drone_free_masks", [])
        for i in range(min(len(tasks), self.max_tasks)):
            if (
                not self._is_padded_task(tasks[i])
                and self._agent_can_take_action(agent_id, i, drone_is_free, drone_free_masks)
            ):
                avail[i + 1] = 1
        return avail

    def get_total_actions(self):
        return self.n_actions

    def render(self):
        return None

    def close(self):
        return None

    def seed(self):
        return None

    def save_replay(self):
        return None
