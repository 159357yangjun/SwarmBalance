import numpy as np
import os
from collections.abc import Mapping
from os.path import dirname, abspath
from copy import deepcopy
from sacred import Experiment, SETTINGS
from sacred.observers import FileStorageObserver
from sacred.utils import apply_backspaces_and_linefeeds
import sys
import torch as th
from utils.logging import get_logger
import yaml
import locale

from run import run


def _configure_console_encoding():
    """Best-effort console encoding setup (helps Windows terminals).

    This avoids garbled output/tracebacks when paths contain non-ASCII.
    """
    try:
        # On Windows, the terminal is often cp936/gbk; on Linux/macOS it's usually utf-8.
        # Default to the preferred encoding to avoid garbled Chinese paths.
        encoding = os.environ.get("PYMARL_CONSOLE_ENCODING") or locale.getpreferredencoding(False) or "utf-8"

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding=encoding, errors="backslashreplace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding=encoding, errors="backslashreplace")
    except Exception:
        pass


_configure_console_encoding()

SETTINGS['CAPTURE_MODE'] = "no" # fd capture may fail on Windows with frontend initialization prints
logger = get_logger()

ex = Experiment("pymarl")
ex.logger = logger
ex.captured_out_filter = apply_backspaces_and_linefeeds

results_path = os.path.join(dirname(dirname(abspath(__file__))), "results")


@ex.main
def my_main(_run, _config, _log):
    # Setting the random seed throughout the modules
    config = config_copy(_config)
    np.random.seed(config["seed"])
    th.manual_seed(config["seed"])
    config['env_args']['seed'] = config["seed"]

    # run the framework
    run(_run, config, _log)


def _get_config(params, arg_name, subfolder):
    config_name = None
    for _i, _v in enumerate(params):
        if _v.split("=")[0] == arg_name:
            config_name = _v.split("=")[1]
            del params[_i]
            break

    if config_name is not None:
        with open(os.path.join(os.path.dirname(__file__), "config", subfolder, "{}.yaml".format(config_name)), "r") as f:
            try:
                config_dict = yaml.safe_load(f)
            except yaml.YAMLError as exc:
                assert False, "{}.yaml error: {}".format(config_name, exc)
        return config_dict or {}

    return {}


def recursive_dict_update(d, u):
    if not u:
        return d
    for k, v in u.items():
        if isinstance(v, Mapping):
            d[k] = recursive_dict_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def _seed_env_args_keys_from_with_overrides(config_dict, params):
    """Pre-create env_args.* keys mentioned in Sacred 'with' overrides.

    Sacred raises ConfigAddedError if a command-line override introduces a new key
    that does not exist in the base config. Since default.yaml has env_args: {},
    we seed placeholder keys so users can do:
            with env=env_drone env_args.max_tasks=... env_args.episode_limit=...
    without requiring an env yaml.
    """
    if not isinstance(config_dict, dict):
        return

    env_args = config_dict.get("env_args")
    if not isinstance(env_args, dict):
        env_args = {}
        config_dict["env_args"] = env_args

    try:
        with_index = params.index("with")
    except ValueError:
        return

    for token in params[with_index + 1 :]:
        if not isinstance(token, str):
            continue
        if not token.startswith("env_args."):
            continue
        if "=" not in token:
            continue

        key = token[len("env_args.") :].split("=", 1)[0].strip()
        if key and key not in env_args:
            env_args[key] = None


def config_copy(config):
    if isinstance(config, dict):
        return {k: config_copy(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [config_copy(v) for v in config]
    else:
        return deepcopy(config)


if __name__ == '__main__':
    params = deepcopy(sys.argv)

    # Get the defaults from default.yaml
    with open(os.path.join(os.path.dirname(__file__), "config", "default.yaml"), "r") as f:
        try:
            config_dict = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            assert False, "default.yaml error: {}".format(exc)

    # Load algorithm and env base configs
    env_config = _get_config(params, "--env-config", "envs")
    alg_config = _get_config(params, "--config", "algs")
    # config_dict = {**config_dict, **env_config, **alg_config}
    config_dict = recursive_dict_update(config_dict, env_config)
    config_dict = recursive_dict_update(config_dict, alg_config)

    # Allow overriding env_args.* from CLI even if env_args is empty in defaults.
    _seed_env_args_keys_from_with_overrides(config_dict, params)

    # now add all the config to sacred
    ex.add_config(config_dict)

    disable_sacred = os.environ.get("PYMARL_DISABLE_SACRED", "").lower() in {"1", "true", "yes", "on"}
    if not disable_sacred:
        logger.info("Saving to FileStorageObserver in results/sacred.")
        file_obs_path = os.path.join(results_path, "sacred")
        ex.observers.append(FileStorageObserver.create(file_obs_path))

    ex.run_commandline(params)

