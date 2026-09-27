"""Statistic registry and stat-name parsing.

A statistic is either *plain* (``mean``) or a *parameterized family* whose
name ends in ``N`` in the registry (``qN``) and is requested on the command
line with a number in place of the ``N`` (``q25``, ``q2.5``, ``mom3``).
Plain names are matched first; a plain name ending in digits (``r2``) is
rejected if it could also be read as a family request.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property

import numpy as np

NONE, FREQ, ERR = None, "freq", "err"
"""Weight modes: unweighted, frequency weights (-w), measurement errors (-e)."""


def wmean(a: np.ndarray, w: np.ndarray | None) -> float:
    """Mean of ``a``, weighted by ``w`` if given."""
    return float(np.mean(a)) if w is None else float(np.dot(a, w) / w.sum())


class Sample:
    """One column of data prepared for the statistics, caching shared intermediates.

    Rows with a missing value (or missing/zero weight) are dropped. ``w`` is
    None when unweighted; with ``mode=ERR`` it holds the inverse variances
    1/sigma**2. ``ref`` is the aligned reference column (-x), if any.
    """

    def __init__(
        self,
        values: np.ndarray,
        weights: np.ndarray | None = None,
        mode: str | None = NONE,
        ref: np.ndarray | None = None,
    ):
        values = np.asarray(values, dtype=float)
        missing = np.isnan(values)
        self.nnan = int(missing.sum())
        valid = ~missing
        if weights is not None:
            valid &= ~np.isnan(weights) & (weights > 0)
        self.mode = mode if weights is not None else NONE
        self.x = values[valid]
        self.w = weights[valid] if weights is not None else None
        self._raw = (values, weights, ref)

    @property
    def nrows(self) -> int:
        return self.x.size

    @cached_property
    def n(self) -> float:
        """Number of values; the total weight with frequency weights."""
        return float(self.w.sum()) if self.mode == FREQ else self.nrows

    @cached_property
    def mean(self) -> float:
        return wmean(self.x, self.w) if self.nrows else np.nan

    @cached_property
    def dev(self) -> np.ndarray:
        """Deviations from the mean."""
        return self.x - self.mean

    @cached_property
    def std(self) -> float:
        """Sample standard deviation (n-1 denominator; n is the total weight if weighted)."""
        if self.n <= 1:
            return np.nan
        ss = np.sum(self.dev**2) if self.w is None else np.dot(self.dev**2, self.w)
        return float(np.sqrt(ss / (self.n - 1)))

    @cached_property
    def sorted(self) -> tuple[np.ndarray, np.ndarray | None]:
        """Values in ascending order, with cumulative weights (None if unweighted)."""
        if self.w is None:
            return np.sort(self.x), None
        order = np.argsort(self.x, kind="stable")
        return self.x[order], np.cumsum(self.w[order])

    @cached_property
    def pair(self) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        """(reference, values, weights) for rows where both are present."""
        values, weights, ref = self._raw
        if ref is None:
            raise ValueError("no reference column")
        valid = ~np.isnan(values) & ~np.isnan(ref)
        if weights is not None:
            valid &= ~np.isnan(weights) & (weights > 0)
        return ref[valid], values[valid], (weights[valid] if weights is not None else None)


@dataclass(frozen=True)
class Stat:
    """A named statistic.

    ``func`` takes a :class:`Sample` and, for parameterized families, the
    numeric parameter; ``param`` describes that parameter (None if plain).
    ``modes`` lists the weight modes the stat is defined for; ``cross`` stats
    compare each column with the reference column (-x).
    """

    name: str
    summary: str
    func: Callable[..., float]
    param: str | None = None
    valid: Callable[[float], bool] | None = None
    modes: frozenset = frozenset({NONE, FREQ})
    cross: bool = False
    empty_ok: bool = False
    """Compute even for a column with no values (otherwise the result is NaN)."""
    text: bool = False
    """The result is a string (e.g. a sparkline), not a number."""

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

    def __call__(self, sample: Sample) -> float | str:
        if sample.nrows == 0 and not self.stat.empty_ok:
            return "" if self.stat.text else np.nan
        with np.errstate(all="ignore"):
            args = (sample, self.arg) if self.stat.param else (sample,)
            result = self.stat.func(*args)
        return result if self.stat.text else float(result)


_PARAM_RE = re.compile(r"^([A-Za-z_]+?)(\d+(?:\.\d*)?)$")


class Registry:
    def __init__(self) -> None:
        self._plain: dict[str, Stat] = {}
        self._families: dict[str, Stat] = {}

    def add(self, stat: Stat) -> None:
        # A plain name ending in digits (r2) is only allowed if it cannot be
        # read as a parameterized request (no family named "r").
        if stat.param:
            clash = [p for p in self._plain if (m := _PARAM_RE.match(p)) and m[1] == stat.name]
            self._families[stat.name] = stat
        else:
            m = _PARAM_RE.match(stat.name)
            clash = [stat.name] if m and m[1] in self._families else []
            self._plain[stat.name] = stat
        if clash:
            raise ValueError(f"stat name {clash[0]!r} is ambiguous with family {stat.name!r}N")

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
