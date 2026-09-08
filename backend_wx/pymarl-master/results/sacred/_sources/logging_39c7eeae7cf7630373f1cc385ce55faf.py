from collections import defaultdict
import logging
import numpy as np


def _scalarize(value):
    """Best-effort convert numeric-ish values (incl. torch tensors) to Python float.

    This keeps logging/aggregation CPU-safe (numpy can't consume cuda tensors).
    """
    # torch.Tensor (cpu/cuda)
    if hasattr(value, "detach"):
        try:
            t = value.detach()
            # Move to CPU for any reductions / numpy compatibility.
            if hasattr(t, "is_cuda") and t.is_cuda:
                t = t.cpu()
            # Scalar tensor
            if hasattr(t, "numel") and callable(t.numel) and t.numel() == 1:
                return float(t.item())
            # Non-scalar tensor -> mean
            if hasattr(t, "float"):
                t = t.float()
            if hasattr(t, "mean") and callable(t.mean):
                return float(t.mean().item())
        except Exception:
            pass

    # numpy scalar / python number
    try:
        return float(value)
    except Exception:
        pass

    # list/ndarray/etc
    try:
        arr = np.asarray(value)
        return float(arr.mean())
    except Exception:
        return float("nan")

class Logger:
    def __init__(self, console_logger):
        self.console_logger = console_logger

        self.use_tb = False
        self.use_sacred = False
        self.use_hdf = False

        self.stats = defaultdict(lambda: [])

    def setup_tb(self, directory_name):
        # Import here so it doesn't have to be installed if you don't use it
        try:
            from tensorboard_logger import configure, log_value  # type: ignore[import-not-found]
        except Exception as e:
            raise ImportError(
                "use_tensorboard=True 需要安装 tensorboard_logger。\n"
                "可在当前环境执行：pip install tensorboard_logger\n"
                "或把 use_tensorboard 设为 False 关闭该功能。"
            ) from e
        configure(directory_name)
        self.tb_logger = log_value
        self.use_tb = True

    def setup_sacred(self, sacred_run_dict):
        self.sacred_info = sacred_run_dict.info
        self.use_sacred = True

    def log_stat(self, key, value, t, to_sacred=True):
        safe_value = _scalarize(value)
        self.stats[key].append((t, safe_value))

        if self.use_tb:
            self.tb_logger(key, safe_value, t)

        if self.use_sacred and to_sacred:
            if key in self.sacred_info:
                self.sacred_info["{}_T".format(key)].append(t)
                self.sacred_info[key].append(safe_value)
            else:
                self.sacred_info["{}_T".format(key)] = [t]
                self.sacred_info[key] = [safe_value]

    def print_recent_stats(self):
        log_str = "Recent Stats | t_env: {:>10} | Episode: {:>8}\n".format(*self.stats["episode"][-1])
        i = 0
        for (k, v) in sorted(self.stats.items()):
            if k == "episode":
                continue
            i += 1
            window = 5 if k != "epsilon" else 1

            vals = [_scalarize(x[1]) for x in self.stats[k][-window:]]
            mean_val = (sum(vals) / max(1, len(vals)))
            item = "{:.4f}".format(mean_val)
            log_str += "{:<25}{:>8}".format(k + ":", item)
            log_str += "\n" if i % 4 == 0 else "\t"
        self.console_logger.info(log_str)


# set up a custom logger
def get_logger():
    logger = logging.getLogger()
    logger.handlers = []
    ch = logging.StreamHandler()
    formatter = logging.Formatter('[%(levelname)s %(asctime)s] %(name)s %(message)s', '%H:%M:%S')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.setLevel('DEBUG')

    return logger

