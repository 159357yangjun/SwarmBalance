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
    parser.add_argument("--print-obs", action="store_true", help="Print observations after reset/each step")
    parser.add_argument("--print-state", action="store_true", help="Print state after reset/each step")
    parser.add_argument(
        "--max-elems",
        type=int,
        default=32,
        help="Max number of elements to print per vector (obs/state)",
    )
    args = parser.parse_args()

    def _fmt_vec(vec):
        try:
            import numpy as np

            arr = np.asarray(vec)
            flat = arr.reshape(-1)
            if flat.size > args.max_elems:
                head = ", ".join(map(lambda x: f"{float(x):.6g}", flat[: args.max_elems]))
                return f"[{head}, ...] (len={flat.size})"
            body = ", ".join(map(lambda x: f"{float(x):.6g}", flat))
            return f"[{body}]"
        except Exception:
            return str(vec)

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

        if args.print_obs:
            for i, one in enumerate(obs):
                print(f"reset obs[{i}]={_fmt_vec(one)}")
        if args.print_state:
            print(f"reset state={_fmt_vec(state)}")

        for t in range(args.steps):
            actions = [0 for _ in range(env.n_agents)]
            reward, terminated, info = env.step(actions)
            print(f"step {t}: reward={reward} terminated={terminated} info_keys={list(info.keys())}")

            if args.print_obs:
                cur_obs = env.get_obs()
                for i, one in enumerate(cur_obs):
                    print(f"step {t} obs[{i}]={_fmt_vec(one)}")
            if args.print_state:
                cur_state = env.get_state()
                print(f"step {t} state={_fmt_vec(cur_state)}")

            if terminated:
                break

        return 0
    finally:
        env.close()


if __name__ == "__main__":
    raise SystemExit(main())
