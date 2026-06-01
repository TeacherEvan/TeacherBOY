"""Init file for src module.

Provides lazy access to heavyweight submodules used by tests and tooling.
"""

from importlib import import_module


def __getattr__(name: str):
    if name == "main":
        module = import_module("src.main")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["main"]
