"""The built-in statistics.

Conventions (kept from the original ``pstats`` so results are unchanged):

* ``stdev``, ``svar``, ``stderr`` and ``ndevN`` use the sample standard
  deviation, s = sqrt(sum((x - mean)**2) / (n - 1)).
* ``momN``, ``devN``, ``ndevN`` and ``absmN`` are plain averages over n.
* ``skew`` and ``kurt`` are the bias-corrected estimators G1 and G2 (``kurt``
  is *excess* kurtosis, 0 for a normal distribution), as in pandas and Excel.
* Quantiles interpolate linearly between order statistics (numpy/pandas
  default).
"""

from __future__ import annotations

import numpy as np

from .registry import Registry, Sample, Stat

_FP_EPS = 1e-14  # pandas treats smaller central-moment sums as exactly zero


def _skew(s: Sample) -> float:
    n = s.n
    if n < 3:
        return np.nan
    d2 = s.dev**2
    m2, m3 = d2.sum(), (d2 * s.dev).sum()
    if abs(m2) < _FP_EPS:
        return 0.0
    if abs(m3) < _FP_EPS:
        m3 = 0.0
    return n * (n - 1) ** 0.5 / (n - 2) * (m3 / m2**1.5)


def _kurt(s: Sample) -> float:
    n = s.n
    if n < 4:
        return np.nan
    d2 = s.dev**2
    m2, m4 = d2.sum(), (d2**2).sum()
    if abs(m2) < _FP_EPS:
        return 0.0
    adj = 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    return n * (n + 1) * (n - 1) * m4 / ((n - 2) * (n - 3) * m2**2) - adj


def _absm(s: Sample, p: float) -> float:
    return np.mean(np.abs(s.dev) ** p)


def _percent(p: float) -> bool:
    return 0 <= p <= 100


BUILTIN = Registry()
for _stat in [
    Stat("n", "number of (non-NaN) values", lambda s: s.n, empty_value=0),
    Stat("min", "minimum", lambda s: s.x.min()),
    Stat("max", "maximum", lambda s: s.x.max()),
    Stat("absmin", "minimum absolute value", lambda s: np.abs(s.x).min()),
    Stat("range", "max - min", lambda s: s.x.max() - s.x.min()),
    Stat("sum", "sum of values", lambda s: s.x.sum(), empty_value=0),
    Stat("mean", "arithmetic mean", lambda s: s.mean),
    Stat("median", "median (50th percentile)", lambda s: np.median(s.x)),
    Stat("stdev", "sample standard deviation s (n-1 denominator)", lambda s: s.std),
    Stat("svar", "sample variance s**2", lambda s: s.std**2),
    Stat("stderr", "standard error of the mean, s/sqrt(n)", lambda s: s.std / np.sqrt(s.n)),
    Stat("skew", "bias-corrected skewness G1", _skew),
    Stat("kurt", "bias-corrected excess kurtosis G2", _kurt),
    Stat("rms", "root mean square, sqrt(mean(x**2))", lambda s: np.sqrt(np.mean(s.x**2))),
    Stat("absdev", "mean absolute deviation from the mean", lambda s: _absm(s, 1)),
    Stat("plq", "lower quartile (25th percentile)", lambda s: np.quantile(s.x, 0.25)),
    Stat("puq", "upper quartile (75th percentile)", lambda s: np.quantile(s.x, 0.75)),
    Stat(
        "q",
        "N-th percentile, e.g. q10, q2.5",
        lambda s, p: np.quantile(s.x, p / 100),
        param="percentile 0-100",
        valid=_percent,
    ),
    Stat("mom", "N-th raw moment, mean(x**N)", lambda s, p: np.mean(s.x**p), param="power"),
    Stat(
        "dev",
        "N-th central moment, mean((x-mean)**N)",
        lambda s, p: np.mean(s.dev**p),
        param="power",
    ),
    Stat(
        "ndev",
        "N-th standardized moment, mean(((x-mean)/s)**N)",
        lambda s, p: np.mean((s.dev / s.std) ** p),
        param="power",
    ),
    Stat("absm", "N-th absolute central moment, mean(|x-mean|**N)", _absm, param="power"),
]:
    BUILTIN.add(_stat)
