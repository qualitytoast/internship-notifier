"""Checker registry: shared hiring-system adapters (this package) + custom checkers (internwatch.checkers)."""
from __future__ import annotations

import importlib
import pkgutil

from .base import REGISTRY, Checker

_loaded = False


def _load_all() -> None:
    global _loaded
    if _loaded:
        return
    from .. import checkers
    for pkg in (__name__, checkers.__name__):
        mod = importlib.import_module(pkg)
        for info in pkgutil.iter_modules(mod.__path__):
            if not info.name.startswith("_") and info.name != "base":
                importlib.import_module(f"{pkg}.{info.name}")
    _loaded = True


def get_checker(type_: str) -> Checker:
    _load_all()
    try:
        return REGISTRY[type_]()
    except KeyError:
        raise KeyError(f"unknown checker type '{type_}'. Known: {', '.join(sorted(REGISTRY))}") from None


def all_types() -> list[str]:
    _load_all()
    return sorted(REGISTRY)
