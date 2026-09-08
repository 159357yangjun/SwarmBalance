from envs import REGISTRY as env_REGISTRY
from functools import partial
from components.episode_buffer import EpisodeBatch
import numpy as np
import torch as th
import csv
import os
from pathlib import Path


class EpisodeRunner:

    def __init__(self, args, logger):
        self.args = args
        self.logger = logger
        self.batch_size = self.args.batch_size_run
        assert self.batch_size == 1

        self.env = env_REGISTRY[self.args.env](**self.args.env_args)
        self.episode_limit = self.env.episode_limit
        self.t = 0

        self.t_env = 0

        self.train_returns = []
        self.test_returns = []
        self.train_stats = {}
        self.test_stats = {}
        self.episode_id = 0
        self.metrics_file = self._resolve_metrics_file()
        self._metrics_header_written = False
        self._metrics_columns = [
            "时间步",
            "模式",
            "总步数",
            "完成任务数",
            "生成任务数",
            "完成率",
            "从生成到分配等待时间",
            "从分配到实际装载上机等待时间",
            "从上机到送达平均时间",
            "从生成到完成总时间平均",
            "从生成到完成总时间最大",
            "超时率",
            "平均时延",
            "优先级1平均时延",
            "优先级2平均时延",
            "优先级3平均时延",
            "总能量消耗",
        ]
        self._ensure_metrics_schema()

        # Log the first run
        self.log_train_stats_t = -1000000

    def setup(self, scheme, groups, preprocess, mac):
        self.new_batch = partial(EpisodeBatch, scheme, groups, self.batch_size, self.episode_limit + 1,
                                 preprocess=preprocess, device=self.args.device)
        self.mac = mac

    def get_env_info(self):
        return self.env.get_env_info()

    def save_replay(self):
        self.env.save_replay()

    def close_env(self):
        self.env.close()

    def reset(self):
        self.batch = self.new_batch()
        self.env.reset()
        self.t = 0

    def run(self, test_mode=False):
        if hasattr(self.env, "set_test_mode"):
            self.env.set_test_mode(test_mode)
        next_episode_id = self.episode_id + 1
        episode_seed = None
        if hasattr(self.env, "set_episode_seed"):
            base_seed = getattr(self.args, "seed", None)
            if base_seed is not None:
                episode_seed = int(base_seed) + int(next_episode_id)
            self.env.set_episode_seed(episode_seed)

        self.reset()
        self.episode_id = next_episode_id

        if episode_seed is not None:
            prefix = "test_" if test_mode else ""
            self.logger.log_stat(prefix + "episode_seed", episode_seed, self.t_env)

        terminated = False
        episode_return = 0
        noop_fastpath_steps = 0
        self.mac.init_hidden(batch_size=self.batch_size)

        while not terminated:

            avail_actions = self.env.get_avail_actions()

            pre_transition_data = {
                "state": [self.env.get_state()],
                "avail_actions": [avail_actions],
                "obs": [self.env.get_obs()]
            }

            self.batch.update(pre_transition_data, ts=self.t)

            avail_actions_arr = np.asarray(avail_actions)
            only_noop = (
                avail_actions_arr.ndim == 2
                and avail_actions_arr.shape[1] > 0
                and np.all(avail_actions_arr[:, 0] == 1)
                and np.all(avail_actions_arr.sum(axis=1) == 1)
            )

            if only_noop:
                actions = th.zeros((self.batch_size, self.env.n_agents), dtype=th.long, device=self.args.device)
                noop_fastpath_steps += 1
            else:
                # Pass the entire batch of experiences up till now to the agents
                # Receive the actions for each agent at this timestep in a batch of size 1
                actions = self.mac.select_actions(self.batch, t_ep=self.t, t_env=self.t_env, test_mode=test_mode)

            reward, terminated, env_info = self.env.step(actions[0])
            episode_return += reward

            post_transition_data = {
                "actions": actions,
                "reward": [(reward,)],
                "terminated": [(terminated != env_info.get("episode_limit", False),)],
            }

            self.batch.update(post_transition_data, ts=self.t)

            self.t += 1

        env_info["noop_fastpath_steps"] = noop_fastpath_steps

        self._write_episode_metrics(env_info, test_mode)

        if hasattr(self.env, "pop_episode_reward_adjustments"):
            adjustments, _ = self.env.pop_episode_reward_adjustments(self.t)
            if adjustments:
                add = th.tensor(adjustments, dtype=self.batch["reward"].dtype, device=self.batch["reward"].device)
                self.batch.data.transition_data["reward"][0, : self.t, 0] += add
                episode_return += float(np.sum(adjustments))

        last_data = {
            "state": [self.env.get_state()],
            "avail_actions": [self.env.get_avail_actions()],
            "obs": [self.env.get_obs()]
        }
        self.batch.update(last_data, ts=self.t)

        # Select actions in the last stored state
        actions = self.mac.select_actions(self.batch, t_ep=self.t, t_env=self.t_env, test_mode=test_mode)
        self.batch.update({"actions": actions}, ts=self.t)

        cur_stats = self.test_stats if test_mode else self.train_stats
        cur_returns = self.test_returns if test_mode else self.train_returns
        log_prefix = "test_" if test_mode else ""
        cur_stats.update({k: cur_stats.get(k, 0) + env_info.get(k, 0) for k in set(cur_stats) | set(env_info)})
        cur_stats["n_episodes"] = 1 + cur_stats.get("n_episodes", 0)
        cur_stats["ep_length"] = self.t + cur_stats.get("ep_length", 0)

        if not test_mode:
            self.t_env += self.t

        cur_returns.append(episode_return)

        if test_mode and (len(self.test_returns) == self.args.test_nepisode):
            self._log(cur_returns, cur_stats, log_prefix)
        elif self.t_env - self.log_train_stats_t >= self.args.runner_log_interval:
            self._log(cur_returns, cur_stats, log_prefix)
            if hasattr(self.mac.action_selector, "epsilon"):
                self.logger.log_stat("epsilon", self.mac.action_selector.epsilon, self.t_env)
            self.log_train_stats_t = self.t_env

        return self.batch

    def _log(self, returns, stats, prefix):
        self.logger.log_stat(prefix + "return_mean", np.mean(returns), self.t_env)
        self.logger.log_stat(prefix + "return_std", np.std(returns), self.t_env)
        returns.clear()

        for k, v in stats.items():
            if k != "n_episodes":
                self.logger.log_stat(prefix + k + "_mean" , v/stats["n_episodes"], self.t_env)
        stats.clear()

    def _write_episode_metrics(self, env_info, test_mode):
        if not isinstance(env_info, dict):
            return

        if "completion_rate" not in env_info:
            return

        os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
        mode = "test" if test_mode else "train"

        need_header = (not self._metrics_header_written) and (not os.path.exists(self.metrics_file))
        with open(self.metrics_file, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if need_header:
                writer.writerow(self._metrics_columns)
                self._metrics_header_written = True
            writer.writerow([
                int(self.t_env),
                mode,
                int(self.t),
                int(env_info.get("total_completed", 0)),
                int(env_info.get("total_generated", 0)),
                float(env_info.get("completion_rate", 0.0)),
                float(env_info.get("avg_generation_to_assignment_wait", 0.0)),
                float(env_info.get("avg_assignment_to_load_wait", 0.0)),
                float(env_info.get("avg_load_to_delivery_time", 0.0)),
                float(env_info.get("avg_generation_to_completion_time", 0.0)),
                float(env_info.get("max_generation_to_completion_time", 0.0)),
                float(env_info.get("timeout_rate", 0.0)),
                float(env_info.get("avg_delay", 0.0)),
                float(env_info.get("avg_delay_priority_1", 0.0)),
                float(env_info.get("avg_delay_priority_2", 0.0)),
                float(env_info.get("avg_delay_priority_3", 0.0)),
                float(env_info.get("total_energy_consumed", 0.0)),
            ])

    def _ensure_metrics_schema(self):
        os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
        if not os.path.exists(self.metrics_file):
            self._metrics_header_written = False
            return

        with open(self.metrics_file, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            existing_columns = reader.fieldnames or []

        if existing_columns == self._metrics_columns:
            self._metrics_header_written = True
            return

        temp_file = self.metrics_file + ".tmp"
        with open(temp_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(self._metrics_columns)
            for row in rows:
                writer.writerow([
                    row.get("时间步", row.get("t_env", "")),
                    row.get("模式", row.get("mode", "")),
                    row.get("总步数", row.get("episode_step", "")),
                    row.get("完成任务数", row.get("total_completed", "")),
                    row.get("生成任务数", row.get("total_generated", "")),
                    row.get("完成率", row.get("completion_rate", "")),
                    row.get("从生成到分配等待时间", row.get("avg_generation_to_assignment_wait", "")),
                    row.get("从分配到实际装载上机等待时间", row.get("avg_assignment_to_load_wait", row.get("avg_wait_time_to_load", ""))),
                    row.get("从上机到送达平均时间", row.get("avg_load_to_delivery_time", row.get("avg_delivery_time", ""))),
                    row.get("从生成到完成总时间平均", row.get("avg_generation_to_completion_time", "")),
                    row.get("从生成到完成总时间最大", row.get("max_generation_to_completion_time", row.get("max_delivery_time", ""))),
                    row.get("超时率", row.get("timeout_rate", "")),
                    row.get("平均时延", row.get("avg_delay", "")),
                    row.get("优先级1平均时延", row.get("avg_delay_priority_1", "")),
                    row.get("优先级2平均时延", row.get("avg_delay_priority_2", "")),
                    row.get("优先级3平均时延", row.get("avg_delay_priority_3", "")),
                    row.get("总能量消耗", row.get("total_energy_consumed", "")),
                ])

        os.replace(temp_file, self.metrics_file)
        self._metrics_header_written = True

    def _resolve_metrics_file(self):
        filename = "backend_wx_metrics.csv"
        metrics_dir = os.environ.get("PYMARL_METRICS_DIR")
        if metrics_dir:
            return str(Path(metrics_dir) / filename)

        sacred_run_dir = getattr(self.args, "sacred_run_dir", None)
        if sacred_run_dir:
            return str(Path(sacred_run_dir) / filename)

        # Fallback: keep compatibility if sacred run dir is unavailable.
        project_root = Path(__file__).resolve().parents[4]
        fallback_dir = project_root / "backend_wx" / "pymarl-master" / "results" / "sacred"
        return str(fallback_dir / "latest" / filename)
