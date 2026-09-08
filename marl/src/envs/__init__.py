from functools import partial
import os
import sys

from .multiagentenv import MultiAgentEnv
from .env_drone import EnvDroneEnv

def env_fn(env, **kwargs) -> MultiAgentEnv:
    return env(**kwargs)

REGISTRY = {}
REGISTRY["env_drone"] = partial(env_fn, env=EnvDroneEnv)


# Optional SMAC/StarCraft II environment support.
# Keep PyMARL usable for custom envs (e.g. env_drone) without installing SC2-related packages.
try:
    from smac.env import StarCraft2Env  # type: ignore
except Exception:
    StarCraft2Env = None
else:
    REGISTRY["sc2"] = partial(env_fn, env=StarCraft2Env)
    if sys.platform == "linux":
        os.environ.setdefault(
            "SC2PATH", os.path.join(os.getcwd(), "3rdparty", "StarCraftII")
        )
