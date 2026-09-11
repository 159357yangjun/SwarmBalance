import json
import socket
import struct
from typing import Any, Dict, List, Sequence, Tuple, Union

import numpy as np

from .multiagentenv import MultiAgentEnv


ShapeType = Union[int, Sequence[int], Tuple[int, ...]]


class UnityTCPEnv(MultiAgentEnv):
    """Unity TCP environment wrapper.

    Protocol: length-prefixed UTF-8 JSON request/response.
    Commands: init, reset, step, close.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        timeout: float = 10.0,
        n_agents: int = 1,
        n_actions: int = 5,
        state_shape: ShapeType = 9,
        obs_shape: ShapeType = 9,
        episode_limit: int = 200,
        auto_reconnect: bool = True,
        **kwargs: Any,
    ):
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.auto_reconnect = bool(auto_reconnect)

        self.n_agents = int(n_agents)
        self._n_actions = int(n_actions)
        self.episode_limit = int(episode_limit)

        self._state_shape = self._shape_to_tuple(state_shape)
        self._obs_shape = self._shape_to_tuple(obs_shape)

        self._socket = None
        self._request_id = 1

        self._state = self._zero_array(self._state_shape)
        self._obs = [self._zero_array(self._obs_shape) for _ in range(self.n_agents)]
        self._avail_actions = np.ones((self.n_agents, self._n_actions), dtype=np.int32)

        self._connect()
        init_resp = self._rpc(
            {
                "cmd": "init",
                "request_id": self._next_request_id(),
                "init": {
                    "n_agents": self.n_agents,
                    "n_actions": self._n_actions,
                    "obs_size": self.get_obs_size(),
                    "state_size": self.get_state_size(),
                    "episode_limit": self.episode_limit,
                },
            }
        )

        # Sync env sizes early so PyMARL's runner (get_env_info) sees the correct values.
        # Unity may return a different agent count or vector sizes than the constructor defaults.
        self._apply_env_info(init_resp)

    def _apply_env_info(self, payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return

        n_agents = payload.get("n_agents")
        n_actions = payload.get("n_actions")
        obs_size = payload.get("obs_size")
        state_size = payload.get("state_size")

        try:
            if n_agents is not None:
                self.n_agents = int(n_agents)
            if n_actions is not None:
                self._n_actions = int(n_actions)
        except Exception:
            pass

        # Unity returns sizes as flat lengths; keep them as 1D shapes.
        try:
            if obs_size is not None:
                self._obs_shape = self._shape_to_tuple(int(obs_size))
            if state_size is not None:
                self._state_shape = self._shape_to_tuple(int(state_size))
        except Exception:
            pass

        # Re-init cached arrays to match updated sizes.
        self._state = self._zero_array(self._state_shape)
        self._obs = [self._zero_array(self._obs_shape) for _ in range(self.n_agents)]
        self._avail_actions = np.ones((self.n_agents, self._n_actions), dtype=np.int32)

    def step(self, actions):
        action_list = self._decode_actions(actions)
        payload = self._rpc(
            {
                "cmd": "step",
                "request_id": self._next_request_id(),
                "actions": action_list,
            }
        )

        reward = float(payload.get("reward", 0.0))
        terminated = bool(payload.get("terminated", False))
        info = payload.get("info", {}) or {}
        if not isinstance(info, dict):
            info = {}

        self._update_cache_from_payload(payload)
        return reward, terminated, info

    def get_obs(self):
        return [obs.copy() for obs in self._obs]

    def get_obs_agent(self, agent_id):
        return self._obs[int(agent_id)].copy()

    def get_obs_size(self):
        return self._shape_for_scheme(self._obs_shape)

    def get_state(self):
        return self._state.copy()

    def get_state_size(self):
        return self._shape_for_scheme(self._state_shape)

    def get_avail_actions(self):
        return self._avail_actions.copy()

    def get_avail_agent_actions(self, agent_id):
        return self._avail_actions[int(agent_id)].copy()

    def get_total_actions(self):
        return self._n_actions

    def reset(self):
        payload = self._rpc({"cmd": "reset", "request_id": self._next_request_id()})
        self._update_cache_from_payload(payload)
        return self.get_obs(), self.get_state()

    def render(self):
        pass

    def close(self):
        try:
            if self._socket is not None:
                try:
                    self._rpc({"cmd": "close", "request_id": self._next_request_id()})
                except Exception:
                    pass
                self._socket.close()
        finally:
            self._socket = None

    def seed(self):
        return None

    def save_replay(self):
        pass

    def get_stats(self):
        return {}

    def _connect(self):
        self._socket = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._socket.settimeout(self.timeout)

    def _ensure_connected(self):
        if self._socket is None:
            self._connect()

    def _rpc(self, message: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_connected()

        raw = None
        try:
            self._send_frame(message)
            raw = self._recv_frame()
        except Exception:
            if not self.auto_reconnect:
                raise
            self.close()
            self._connect()
            self._send_frame(message)
            raw = self._recv_frame()

        if not isinstance(raw, dict):
            raise ValueError("Unity TCP response must be a JSON object.")

        if not raw.get("ok", True):
            raise RuntimeError(f"Unity TCP error: {raw.get('error', 'unknown error')}")

        return raw

    def _send_frame(self, payload: Dict[str, Any]):
        body = json.dumps(payload).encode("utf-8")
        header = struct.pack("<I", len(body))
        self._socket.sendall(header + body)

    def _recv_frame(self) -> Dict[str, Any]:
        header = self._recv_exact(4)
        if header is None:
            raise ConnectionError("Connection closed while reading frame header.")

        length = struct.unpack("<I", header)[0]
        if length <= 0:
            raise ValueError("Invalid frame length from Unity TCP server.")

        body = self._recv_exact(length)
        if body is None:
            raise ConnectionError("Connection closed while reading frame payload.")

        return json.loads(body.decode("utf-8"))

    def _recv_exact(self, size: int):
        chunks = []
        remaining = size
        while remaining > 0:
            chunk = self._socket.recv(remaining)
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _update_cache_from_payload(self, payload: Dict[str, Any]):
        state = payload.get("state")
        obs = payload.get("obs")
        avail_actions = payload.get("avail_actions")

        if state is None or obs is None or avail_actions is None:
            raise ValueError("Unity TCP response must include state, obs, avail_actions.")

        state_arr = np.asarray(state, dtype=np.float32)
        if state_arr.shape != self._state_shape:
            raise ValueError(f"State shape mismatch, expected {self._state_shape}, got {state_arr.shape}.")

        obs_list = []
        if not isinstance(obs, list):
            raise ValueError("obs must be a list.")

        for i, item in enumerate(obs):
            values = item.get("values") if isinstance(item, dict) else None
            arr = np.asarray(values, dtype=np.float32)
            if arr.shape != self._obs_shape:
                raise ValueError(f"Obs[{i}] shape mismatch, expected {self._obs_shape}, got {arr.shape}.")
            obs_list.append(arr)

        avail_list = []
        if not isinstance(avail_actions, list):
            raise ValueError("avail_actions must be a list.")

        for i, item in enumerate(avail_actions):
            values = item.get("values") if isinstance(item, dict) else None
            arr = np.asarray(values, dtype=np.int32)
            if arr.shape != (self._n_actions,):
                raise ValueError(f"avail_actions[{i}] shape mismatch, expected {(self._n_actions,)}, got {arr.shape}.")
            avail_list.append(arr)

        if len(obs_list) != len(avail_list):
            raise ValueError("obs and avail_actions must have the same number of agents.")

        self.n_agents = len(obs_list)
        self._state = state_arr
        self._obs = obs_list
        self._avail_actions = np.asarray(avail_list, dtype=np.int32)

    def _decode_actions(self, actions: Any) -> List[int]:
        if hasattr(actions, "detach"):
            arr = actions.detach().cpu().numpy()
        else:
            arr = np.asarray(actions)

        arr = np.asarray(arr).reshape(-1)
        out = [int(x) for x in arr.tolist()]

        for action in out:
            if action < 0 or action >= self._n_actions:
                raise ValueError(f"Action index out of range: {action}, expected [0, {self._n_actions - 1}].")

        return out

    def _next_request_id(self) -> int:
        rid = self._request_id
        self._request_id += 1
        return rid

    @staticmethod
    def _shape_to_tuple(shape: ShapeType) -> Tuple[int, ...]:
        if isinstance(shape, int):
            return (shape,)
        if isinstance(shape, tuple):
            return shape
        if isinstance(shape, list):
            return tuple(shape)
        raise TypeError(f"Unsupported shape type: {type(shape)}")

    @staticmethod
    def _shape_for_scheme(shape: Tuple[int, ...]) -> Union[int, Tuple[int, ...]]:
        if len(shape) == 1:
            return shape[0]
        return shape

    @staticmethod
    def _zero_array(shape: Tuple[int, ...]) -> np.ndarray:
        return np.zeros(shape, dtype=np.float32)
