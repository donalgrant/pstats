"""Statistic registry and stat-name parsing.

A statistic is either *plain* (``mean``) or a *parameterized family* whose
name ends in ``N`` in the registry (``qN``) and is requested on the command
line with a number in place of the ``N`` (``q25``, ``q2.5``, ``mom3``).
Plain stat names never end in a digit, so the two forms cannot collide.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property

import numpy as np


class Sample:
    """One column of data with NaNs removed, caching shared intermediates."""

    def __init__(self, values: np.ndarray):
        values = np.asarray(values, dtype=float)
        self.x = values[~np.isnan(values)]

    @property
    def n(self) -> int:
        return self.x.size

    @cached_property
    def mean(self) -> float:
        return float(self.x.mean()) if self.n else np.nan

    @cached_property
    def dev(self) -> np.ndarray:
        """Deviations from the mean."""
        return self.x - self.mean

    @cached_property
    def std(self) -> float:
        """Sample standard deviation (ddof=1)."""
        return float(np.sqrt(np.sum(self.dev**2) / (self.n - 1))) if self.n > 1 else np.nan


@dataclass(frozen=True)
class Stat:
    """A named statistic.

    ``func`` takes a :class:`Sample` and, for parameterized families, the
    numeric parameter; ``param`` describes that parameter (None if plain).
    """

    name: str
    summary: str
    func: Callable[..., float]
    param: str | None = None
    valid: Callable[[float], bool] | None = None
    empty_value: float = np.nan
    """Result for an empty column (e.g. 0 for ``n`` and ``sum``)."""

    @property
    def display_name(self) -> str:
        return self.name + "N" if self.param else self.name


class UnknownStatError(ValueError):
    pass


@dataclass(frozen=True)
class Request:
    """A stat requested on the command line, bound to its parameter."""

    label: str
    stat: Stat
    arg: float | None = None

    def __call__(self, sample: Sample) -> float:
        if sample.n == 0:
            return self.stat.empty_value
        with np.errstate(all="ignore"):
            if self.stat.param:
                return float(self.stat.func(sample, self.arg))
            return float(self.stat.func(sample))


_PARAM_RE = re.compile(r"^([A-Za-z_]+?)(\d+(?:\.\d*)?)$")


class Registry:
    def __init__(self) -> None:
        self._plain: dict[str, Stat] = {}
        self._families: dict[str, Stat] = {}

    def add(self, stat: Stat) -> None:
        if stat.param:
            self._families[stat.name] = stat
        else:
            if stat.name[-1].isdigit():
                raise ValueError(f"plain stat name may not end in a digit: {stat.name}")
            self._plain[stat.name] = stat

    def __iter__(self):
        return iter([*self._plain.values(), *self._families.values()])

    def resolve(self, label: str) -> Request:
        """Turn a command-line stat name into a bound :class:`Request`."""
        if label in self._plain:
            return Request(label, self._plain[label])
        m = _PARAM_RE.match(label)
        if m and m.group(1) in self._families:
            stat, arg = self._families[m.group(1)], float(m.group(2))
            if stat.valid and not stat.valid(arg):
                raise UnknownStatError(f"{label!r}: {stat.param} out of range")
            return Request(label, stat, arg)
        if label.endswith("N") and label[:-1] in self._families:
            raise UnknownStatError(
                f"statistic {label!r} needs a number in place of N (e.g. {label[:-1]}25)"
            )
        if m:
            raise UnknownStatError(f"no parameterized statistic {m.group(1)!r}N")
        raise UnknownStatError(f"unknown statistic {label!r}")
