"""The built-in statistics.

Conventions (kept from the original ``pstats`` so results are unchanged):

* ``stdev``, ``svar``, ``stderr`` and ``ndevN`` use the sample standard
  deviation, s = sqrt(sum((x - mean)**2) / (n - 1)); ``pstdev``/``pvar`` use n.
* ``momN``, ``devN``, ``ndevN`` and ``absmN`` are plain averages over n.
* ``skew`` and ``kurt`` are the bias-corrected estimators G1 and G2 (``kurt``
  is *excess* kurtosis, 0 for a normal distribution), as in pandas and Excel.
* Quantiles interpolate linearly between order statistics (numpy/pandas
  default).

With frequency weights (-w) every statistic is computed as if each row were
repeated w times (n is the total weight). With measurement errors (-e) the
weights are 1/sigma**2 and only statistics with a standard inverse-variance
definition are available.
"""

from __future__ import annotations

import math

import numpy as np

from .registry import ERR, FREQ, NONE, Registry, Sample, Stat, wmean

_FP_EPS = 1e-14  # pandas treats smaller central-moment sums as exactly zero
_MAD_TO_SIGMA = 1.482602218505602  # 1 / Phi^-1(3/4): MAD -> sigma for normal data
ALL = frozenset({NONE, FREQ, ERR})
UNWEIGHTED = frozenset({NONE})


def _wsum(a: np.ndarray, w: np.ndarray | None) -> float:
    return float(np.sum(a)) if w is None else float(np.dot(a, w))


def _quantile(s: Sample, p: float) -> float:
    """p-quantile (0..1), linear interpolation; weighted as replicated rows."""
    if s.w is None:
        return float(np.quantile(s.x, p))  # partial sort: faster than s.sorted
    xs, cw = s.sorted
    h = max((cw[-1] - 1) * p, 0.0)  # position in the (virtually) replicated data
    lo = math.floor(h)
    i = min(np.searchsorted(cw, lo, side="right"), xs.size - 1)
    j = min(np.searchsorted(cw, lo + 1, side="right"), xs.size - 1)
    return float(xs[i] + (h - lo) * (xs[j] - xs[i]))


def _mad(s: Sample) -> float:
    return _quantile(Sample(np.abs(s.x - _quantile(s, 0.5)), s.w, s.mode), 0.5)


def _central_sums(s: Sample) -> tuple[float, float, float]:
    d2 = s.dev**2
    return _wsum(d2, s.w), _wsum(d2 * s.dev, s.w), _wsum(d2**2, s.w)


def _skew(s: Sample) -> float:
    n = s.n
    if n < 3:
        return np.nan
    m2, m3, _ = _central_sums(s)
    if abs(m2) < _FP_EPS:
        return 0.0
    if abs(m3) < _FP_EPS:
        m3 = 0.0
    return n * (n - 1) ** 0.5 / (n - 2) * (m3 / m2**1.5)


def _kurt(s: Sample) -> float:
    n = s.n
    if n < 4:
        return np.nan
    m2, _, m4 = _central_sums(s)
    if abs(m2) < _FP_EPS:
        return 0.0
    adj = 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    return n * (n + 1) * (n - 1) * m4 / ((n - 2) * (n - 3) * m2**2) - adj


def _absm(s: Sample, p: float) -> float:
    return wmean(np.abs(s.dev) ** p, s.w)


def _pvar(s: Sample) -> float:
    return wmean(s.dev**2, s.w)


def _stderr(s: Sample) -> float:
    if s.mode == ERR:
        return 1 / np.sqrt(s.w.sum())
    return s.std / np.sqrt(s.n)


def _chi2(s: Sample) -> float:
    return float(np.dot(s.dev**2, s.w))


def _gmean(s: Sample) -> float:
    return float(np.exp(wmean(np.log(s.x), s.w))) if (s.x > 0).all() else np.nan


def _hmean(s: Sample) -> float:
    return 1 / wmean(1 / s.x, s.w) if (s.x > 0).all() else np.nan


def _trimmean(s: Sample, p: float) -> float:
    """Mean after removing p percent of values from each end (as scipy.stats.trim_mean)."""
    xs, _ = s.sorted
    k = int(p / 100 * xs.size)
    return float(xs[k : xs.size - k].mean())


def _mode(s: Sample) -> float:
    values, inverse = np.unique(s.x, return_inverse=True)
    counts = np.bincount(inverse.ravel(), weights=s.w)
    return float(values[np.argmax(counts)])  # ties: smallest value


# -- statistics between each column and the reference column (-x) ----------------


def _pair_moments(s: Sample):
    """Weighted sums for the pair (r, y): total weight, means, and centered sums."""
    r, y, w = s.pair
    ww = np.ones_like(r) if w is None else w
    sw = ww.sum()
    rm, ym = np.dot(ww, r) / sw, np.dot(ww, y) / sw
    dr, dy = r - rm, y - ym
    return r.size, sw, rm, ym, np.dot(ww, dr * dr), np.dot(ww, dy * dy), np.dot(ww, dr * dy)


def _cov(s: Sample) -> float:
    rows, sw, _, _, _, _, sry = _pair_moments(s)
    n = sw if s.mode == FREQ else rows
    return sry / (n - 1) if n > 1 else np.nan


def _corr(s: Sample) -> float:
    rows, _, _, _, srr, syy, sry = _pair_moments(s)
    return sry / np.sqrt(srr * syy) if rows > 1 else np.nan


def _ranks(a: np.ndarray) -> np.ndarray:
    """1-based ranks, ties given their average rank."""
    _, inverse, counts = np.unique(a, return_inverse=True, return_counts=True)
    return (np.cumsum(counts) - (counts - 1) / 2)[inverse.ravel()]


def _rcorr(s: Sample) -> float:
    r, y, _ = s.pair
    if r.size < 2:
        return np.nan
    return _corr(Sample(_ranks(y), ref=_ranks(r)))


def _fit(s: Sample) -> dict[str, float]:
    """Straight-line fit y = intercept + slope * r (weighted least squares if weighted)."""
    rows, sw, rm, ym, srr, syy, sry = _pair_moments(s)
    nan = dict.fromkeys(("slope", "intercept", "slope_err", "intercept_err"), np.nan)
    if rows < 2 or srr == 0:
        return {**nan, "r2": np.nan, "rmsres": np.nan, "chi2": np.nan, "dof": np.nan}
    slope = sry / srr
    intercept = ym - slope * rm
    ss_res = max(syy - slope * sry, 0.0)  # weighted sum of squared residuals
    n = sw if s.mode == FREQ else rows
    if s.mode == ERR:
        var_slope = 1 / srr  # errors known: no rescaling by the residuals
    else:
        var_slope = ss_res / (n - 2) / srr if n > 2 else np.nan
    var_intercept = var_slope * (srr / sw + rm**2)
    return {
        "slope": slope,
        "intercept": intercept,
        "slope_err": np.sqrt(var_slope),
        "intercept_err": np.sqrt(var_intercept),
        "r2": 1 - ss_res / syy if syy > 0 else np.nan,
        "rmsres": np.sqrt(ss_res / sw),
        "chi2": ss_res,
        "dof": rows - 2,
    }


def _rchi2fit(s: Sample) -> float:
    f = _fit(s)
    return f["chi2"] / f["dof"] if f["dof"] > 0 else np.nan


def _fit_stat(key: str):
    return lambda s: _fit(s)[key]


def _percent(p: float) -> bool:
    return 0 <= p <= 100


def _half_percent(p: float) -> bool:
    return 0 <= p < 50


BUILTIN = Registry()
for _stat in [
    Stat("n", "number of values (total weight with -w)", lambda s: s.n, modes=ALL, empty_ok=True),
    Stat("nrows", "number of rows with a value", lambda s: s.nrows, modes=ALL, empty_ok=True),
    Stat("nnan", "number of missing (NaN) values", lambda s: s.nnan, modes=ALL, empty_ok=True),
    Stat("min", "minimum", lambda s: s.x.min(), modes=ALL),
    Stat("max", "maximum", lambda s: s.x.max(), modes=ALL),
    Stat("absmin", "minimum absolute value", lambda s: np.abs(s.x).min(), modes=ALL),
    Stat("range", "max - min", lambda s: s.x.max() - s.x.min(), modes=ALL),
    Stat("sum", "sum of values", lambda s: _wsum(s.x, s.w), empty_ok=True),
    Stat(
        "mean", "arithmetic mean (inverse-variance weighted with -e)", lambda s: s.mean, modes=ALL
    ),
    Stat("median", "median (50th percentile)", lambda s: _quantile(s, 0.5)),
    Stat("mode", "most frequent value (smallest if tied)", _mode),
    Stat("gmean", "geometric mean (NaN unless all values > 0)", _gmean),
    Stat("hmean", "harmonic mean (NaN unless all values > 0)", _hmean),
    Stat("stdev", "sample standard deviation s (n-1 denominator)", lambda s: s.std),
    Stat("svar", "sample variance s**2", lambda s: s.std**2),
    Stat("pstdev", "population standard deviation (n denominator)", lambda s: np.sqrt(_pvar(s))),
    Stat("pvar", "population variance (n denominator)", _pvar),
    Stat(
        "stderr",
        "standard error of the mean, s/sqrt(n); 1/sqrt(sum(1/sigma**2)) with -e",
        _stderr,
        modes=ALL,
    ),
    Stat("cv", "coefficient of variation, stdev/mean", lambda s: s.std / s.mean),
    Stat("skew", "bias-corrected skewness G1", _skew),
    Stat("kurt", "bias-corrected excess kurtosis G2", _kurt),
    Stat("rms", "root mean square, sqrt(mean(x**2))", lambda s: np.sqrt(wmean(s.x**2, s.w))),
    Stat("absdev", "mean absolute deviation from the mean", lambda s: _absm(s, 1)),
    Stat("mad", "median absolute deviation from the median", _mad),
    Stat(
        "smad",
        "1.4826 * mad: robust estimate of sigma for normal data",
        lambda s: _MAD_TO_SIGMA * _mad(s),
    ),
    Stat("plq", "lower quartile (25th percentile)", lambda s: _quantile(s, 0.25)),
    Stat("puq", "upper quartile (75th percentile)", lambda s: _quantile(s, 0.75)),
    Stat(
        "iqr", "interquartile range, puq - plq", lambda s: _quantile(s, 0.75) - _quantile(s, 0.25)
    ),
    Stat(
        "chi2",
        "sum(((x-mean)/sigma)**2) about the weighted mean (-e only)",
        _chi2,
        modes=frozenset({ERR}),
    ),
    Stat(
        "rchi2",
        "chi2 / (n-1) (-e only)",
        lambda s: _chi2(s) / (s.nrows - 1) if s.nrows > 1 else np.nan,
        modes=frozenset({ERR}),
    ),
    Stat(
        "q",
        "N-th percentile, e.g. q10, q2.5",
        lambda s, p: _quantile(s, p / 100),
        param="percentile 0-100",
        valid=_percent,
    ),
    Stat(
        "trimmean",
        "mean after dropping N percent from each end, e.g. trimmean10",
        _trimmean,
        param="percentage 0-50",
        valid=_half_percent,
        modes=UNWEIGHTED,
    ),
    Stat("mom", "N-th raw moment, mean(x**N)", lambda s, p: wmean(s.x**p, s.w), param="power"),
    Stat(
        "dev",
        "N-th central moment, mean((x-mean)**N)",
        lambda s, p: wmean(s.dev**p, s.w),
        param="power",
    ),
    Stat(
        "ndev",
        "N-th standardized moment, mean(((x-mean)/s)**N)",
        lambda s, p: wmean((s.dev / s.std) ** p, s.w),
        param="power",
    ),
    Stat("absm", "N-th absolute central moment, mean(|x-mean|**N)", _absm, param="power"),
    # between each column (y) and the reference column (x), selected with -x
    Stat("corr", "Pearson correlation with the reference column", _corr, cross=True),
    Stat(
        "rcorr",
        "Spearman rank correlation with the reference column",
        _rcorr,
        cross=True,
        modes=UNWEIGHTED,
    ),
    Stat("cov", "sample covariance with the reference column", _cov, cross=True),
    Stat(
        "slope",
        "slope b of the least-squares fit y = a + b*x",
        _fit_stat("slope"),
        cross=True,
        modes=ALL,
    ),
    Stat("intercept", "intercept a of the fit", _fit_stat("intercept"), cross=True, modes=ALL),
    Stat("slope_err", "standard error of the slope", _fit_stat("slope_err"), cross=True, modes=ALL),
    Stat(
        "intercept_err",
        "standard error of the intercept",
        _fit_stat("intercept_err"),
        cross=True,
        modes=ALL,
    ),
    Stat(
        "r2", "coefficient of determination R**2 of the fit", _fit_stat("r2"), cross=True, modes=ALL
    ),
    Stat("rmsres", "RMS of the fit residuals", _fit_stat("rmsres"), cross=True, modes=ALL),
    Stat(
        "chi2fit",
        "chi-square of the fit residuals (-e only)",
        _fit_stat("chi2"),
        cross=True,
        modes=frozenset({ERR}),
    ),
    Stat(
        "rchi2fit",
        "chi2fit / (n-2) (-e only)",
        _rchi2fit,
        cross=True,
        modes=frozenset({ERR}),
    ),
]:
    BUILTIN.add(_stat)
