import torch as th
from torch.distributions import Categorical
from .epsilon_schedules import DecayThenFlatSchedule

REGISTRY = {}


class MultinomialActionSelector():

    def __init__(self, args):
        self.args = args

        self.schedule = DecayThenFlatSchedule(args.epsilon_start, args.epsilon_finish, args.epsilon_anneal_time,
                                              decay="linear")
        self.epsilon = self.schedule.eval(0)
        self.test_greedy = getattr(args, "test_greedy", True)

    def select_action(self, agent_inputs, avail_actions, t_env, test_mode=False):
        masked_policies = agent_inputs.clone()
        masked_policies[avail_actions == 0.0] = 0.0

        self.epsilon = self.schedule.eval(t_env)

        if test_mode and self.test_greedy:
            picked_actions = masked_policies.max(dim=2)[1]
        else:
            picked_actions = Categorical(masked_policies).sample().long()

        return picked_actions


REGISTRY["multinomial"] = MultinomialActionSelector


class EpsilonGreedyActionSelector():

    def __init__(self, args):
        self.args = args

        self.schedule = DecayThenFlatSchedule(args.epsilon_start, args.epsilon_finish, args.epsilon_anneal_time,
                                              decay="linear")
        self.epsilon = self.schedule.eval(0)

    def select_action(self, agent_inputs, avail_actions, t_env, test_mode=False):

        # Assuming agent_inputs is a batch of Q-Values for each agent bav
        self.epsilon = self.schedule.eval(t_env)

        if test_mode:
            # Greedy action selection only
            self.epsilon = 0.0

        # mask actions that are excluded from selection
        masked_q_values = agent_inputs.clone()
        masked_q_values[avail_actions == 0.0] = -float("inf")  # should never be selected!

        random_numbers = th.rand_like(agent_inputs[:, :, 0])
        pick_random = (random_numbers < self.epsilon).long()
        if getattr(self.args, "unique_task_assignment", False):
            random_actions = self._select_unique_random_actions(avail_actions)
            greedy_actions = self._select_unique_task_actions(masked_q_values, avail_actions)
        else:
            random_actions = Categorical(avail_actions.float()).sample().long()
            greedy_actions = masked_q_values.max(dim=2)[1]

        picked_actions = pick_random * random_actions + (1 - pick_random) * greedy_actions
        return picked_actions

    def _select_unique_random_actions(self, avail_actions):
        """Random exploration without duplicate non-NoOp task actions in a batch item."""
        bs, n_agents, _ = avail_actions.shape
        noop_action = int(getattr(self.args, "noop_action", 0))
        out = th.full((bs, n_agents), noop_action, dtype=th.long, device=avail_actions.device)

        for b in range(bs):
            used_tasks = set()
            agent_order = th.randperm(n_agents, device=avail_actions.device).tolist()
            for agent_idx in agent_order:
                valid = th.nonzero(avail_actions[b, agent_idx] > 0, as_tuple=False).view(-1).tolist()
                filtered = [
                    int(action)
                    for action in valid
                    if int(action) == noop_action or int(action) not in used_tasks
                ]
                if not filtered:
                    continue
                choice_idx = int(th.randint(len(filtered), (1,), device=avail_actions.device).item())
                action = filtered[choice_idx]
                out[b, agent_idx] = action
                if action != noop_action:
                    used_tasks.add(action)

        return out

    def _select_unique_task_actions(self, masked_q_values, avail_actions):
        """Greedy matching to avoid duplicate non-NoOp tasks (fast for 10 agents)."""
        bs, n_agents, _ = masked_q_values.shape
        noop_action = int(getattr(self.args, "noop_action", 0))
        out = th.zeros((bs, n_agents), dtype=th.long, device=masked_q_values.device)

        for b in range(bs):
            picked = [noop_action for _ in range(n_agents)]
            used_tasks = set()
            used_agents = set()

            # Build candidate (q, agent, action) list for non-NoOp actions only.
            candidates = []
            for agent_idx in range(n_agents):
                valid = th.nonzero(avail_actions[b, agent_idx] > 0, as_tuple=False).view(-1)
                if valid.numel() == 0:
                    continue
                qvals = masked_q_values[b, agent_idx, valid]
                for j in range(valid.numel()):
                    action = int(valid[j].item())
                    if action == noop_action:
                        continue
                    q = float(qvals[j].item())
                    candidates.append((q, agent_idx, action))

            # Greedy maximum weight matching over (agent, action) pairs.
            candidates.sort(key=lambda x: x[0], reverse=True)
            for _, agent_idx, action in candidates:
                if agent_idx in used_agents or action in used_tasks:
                    continue
                picked[agent_idx] = action
                used_agents.add(agent_idx)
                used_tasks.add(action)

            out[b] = th.tensor(picked, dtype=th.long, device=masked_q_values.device)

        return out


REGISTRY["epsilon_greedy"] = EpsilonGreedyActionSelector
