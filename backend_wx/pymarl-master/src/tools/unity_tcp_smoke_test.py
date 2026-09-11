import argparse
import os
import sys


def _ensure_src_on_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, ".."))
    src = os.path.join(root, "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def main() -> int:
    _ensure_src_on_path()

    from envs.unity_tcp_env import UnityTCPEnv

    parser = argparse.ArgumentParser(description="Smoke test for UnityTCPEnv (connect/init/reset/step/close).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--n-agents", type=int, default=1)
    parser.add_argument("--n-actions", type=int, default=5)
    parser.add_argument("--obs-size", type=int, default=9)
    parser.add_argument("--state-size", type=int, default=9)
    parser.add_argument("--steps", type=int, default=3)
    args = parser.parse_args()

    env = UnityTCPEnv(
        host=args.host,
        port=args.port,
        timeout=args.timeout,
        n_agents=args.n_agents,
        n_actions=args.n_actions,
        obs_shape=args.obs_size,
        state_shape=args.state_size,
    )

    try:
        obs, state = env.reset()
        print(f"connected ok | obs_agents={len(obs)} state_shape={state.shape}")

        for t in range(args.steps):
            actions = [0 for _ in range(env.n_agents)]
            reward, terminated, info = env.step(actions)
            print(f"step {t}: reward={reward} terminated={terminated} info_keys={list(info.keys())}")
            if terminated:
                break

        return 0
    finally:
        env.close()


if __name__ == "__main__":
    raise SystemExit(main())
