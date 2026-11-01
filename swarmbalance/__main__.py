"""Canonical console, evaluation and diagnostic commands."""
import argparse
import importlib
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="swarmbalance", description="SwarmBalance simulation platform")
    parser.add_argument("command", choices=("console", "evaluate", "selfcheck"))
    if not argv:
        parser.print_help()
        return
    command = parser.parse_args(argv[:1]).command
    module = importlib.import_module(f"swarmbalance.cli.{command}")
    return module.main(argv[1:])


if __name__ == "__main__":
    main()
