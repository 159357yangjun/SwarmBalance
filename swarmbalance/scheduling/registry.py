"""The single registry for algorithm metadata and scheduler construction."""
from dataclasses import asdict, dataclass
import importlib
import importlib.util

from swarmbalance.contracts.scheduling import Scheduler


@dataclass(frozen=True)
class AlgorithmDescriptor:
    key: str
    label: str
    available: bool
    reason: str = ""

    def as_dict(self):
        return asdict(self)


_STRATEGIES = {
    "greedy": ("Greedy 贪心", "swarmbalance.scheduling.greedy", "GreedyScheduler"),
    "pso": ("PSO 粒子群", "swarmbalance.scheduling.pso", "PSOScheduler"),
    "ga": ("GA 遗传", "swarmbalance.scheduling.ga", "GAScheduler"),
    "ortools": ("OR-Tools", "swarmbalance.scheduling.ortools", "ORToolsScheduler"),
}
ALGORITHM_KEYS = tuple(_STRATEGIES)
_OPTIONAL_REASON = "未安装 ortools；其它算法仍可正常运行"


def _available(name):
    if name != "ortools":
        return True
    try:
        return importlib.util.find_spec("ortools") is not None
    except (ImportError, ValueError):
        return False


def list_algorithms():
    return [AlgorithmDescriptor(key, label, _available(key),
                                "" if _available(key) else _OPTIONAL_REASON)
            for key, (label, _, _) in _STRATEGIES.items()]


def create_scheduler(name, *, num_drones, seed, config_path=None) -> Scheduler:
    if name not in _STRATEGIES:
        raise ValueError(f"未知算法: {name}")
    if not _available(name):
        raise RuntimeError("OR-Tools 未安装：pip install ortools")
    _, module_name, class_name = _STRATEGIES[name]
    module = importlib.import_module(module_name)
    if name == "ortools" and not module.ORTOOLS_AVAILABLE:
        raise RuntimeError("OR-Tools 不可用：pip install ortools")
    cls = getattr(module, class_name)
    if name == "greedy":
        return cls()
    return cls(num_drones=num_drones, seed=seed, verbose=False, config_path=config_path)
