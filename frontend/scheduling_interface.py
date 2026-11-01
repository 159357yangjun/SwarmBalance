"""Compatibility entrypoint; implementation lives in swarmbalance.contracts.scheduling."""
import importlib as _importlib
import sys as _sys
from pathlib import Path as _Path

_root = str(_Path(__file__).resolve().parents[1])
if _root not in _sys.path:
    _sys.path.insert(0, _root)
_implementation = _importlib.import_module("swarmbalance.contracts.scheduling")
if __name__ == "__main__":
    _implementation.main()
else:
    _sys.modules[__name__] = _implementation
