"""Check every statistic against independent reference implementations."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from stats_cli.registry import Sample
from stats_cli.stats import BUILTIN

rng = np.random.default_rng(7)
DATA = [
    rng.normal(3, 2, 1000),
    rng.exponential(1.5, 57),
    np.array([4.0, -1.0, 2.5, 8.0, 0.0]),
]


def calc(label, x):
    return BUILTIN.resolve(label)(Sample(x))


REFERENCE = {
    "n": lambda x: len(x),
    "min": np.min,
    "max": np.max,
    "absmin": lambda x: np.abs(x).min(),
    "range": np.ptp,
    "sum": np.sum,
    "mean": np.mean,
    "median": np.median,
    "stdev": lambda x: np.std(x, ddof=1),
    "svar": lambda x: np.var(x, ddof=1),
    "stderr": lambda x: sps.sem(x),
    "skew": lambda x: pd.Series(x).skew(),
    "kurt": lambda x: pd.Series(x).kurt(),
    "rms": lambda x: np.sqrt(np.mean(x**2)),
    "absdev": lambda x: np.mean(np.abs(x - x.mean())),
    "plq": lambda x: pd.Series(x).quantile(0.25),
    "puq": lambda x: pd.Series(x).quantile(0.75),
    "q2.5": lambda x: pd.Series(x).quantile(0.025),
    "q90": lambda x: np.percentile(x, 90),
    "mom2": lambda x: sps.moment(x, 2, center=0),
    "dev3": lambda x: sps.moment(x, 3),
    "ndev3": lambda x: sps.moment(x, 3) / np.std(x, ddof=1) ** 3,
    "absm1.5": lambda x: np.mean(np.abs(x - x.mean()) ** 1.5),
}


@pytest.mark.parametrize("label", list(REFERENCE))  # snapshot: original stats only
@pytest.mark.parametrize("i", range(len(DATA)))
def test_against_reference(label, i):
    x = DATA[i]
    assert calc(label, x) == pytest.approx(REFERENCE[label](x), rel=1e-10, abs=1e-12)


REFERENCE.update(
    {
        "nrows": lambda x: len(x),
        "nnan": lambda x: 0,
        "mode": lambda x: sps.mode(np.round(x, 1)).mode,
        "gmean": lambda x: sps.gmean(x) if (x > 0).all() else np.nan,
        "hmean": lambda x: sps.hmean(x) if (x > 0).all() else np.nan,
        "pstdev": lambda x: np.std(x),
        "pvar": lambda x: np.var(x),
        "cv": lambda x: sps.variation(x, ddof=1),
        "mad": lambda x: sps.median_abs_deviation(x),
        "smad": lambda x: sps.median_abs_deviation(x, scale="normal"),
        "iqr": lambda x: sps.iqr(x),
        "trimmean10": lambda x: sps.trim_mean(x, 0.1),
        "trimmean25": lambda x: sps.trim_mean(x, 0.25),
    }
)
ROUNDED = {"mode"}  # evaluated on data rounded to 0.1 so that repeats exist


@pytest.mark.parametrize(
    "label",
    [
        "nrows",
        "nnan",
        "mode",
        "gmean",
        "hmean",
        "pstdev",
        "pvar",
        "cv",
        "mad",
        "smad",
        "iqr",
        "trimmean10",
        "trimmean25",
    ],
)
@pytest.mark.parametrize("i", range(len(DATA)))
def test_new_against_reference(label, i):
    x = np.round(DATA[i], 1) if label in ROUNDED else DATA[i]
    got, want = calc(label, x), REFERENCE[label](x)
    np.testing.assert_allclose(got, want, rtol=1e-10, atol=1e-12)


# -- cross-column statistics ---------------------------------------------------

rx = np.linspace(0, 10, 40)
ry = 1.5 - 0.7 * rx + rng.normal(0, 1, rx.size)
rsig = rng.uniform(0.5, 2, rx.size)


def cross(label, y=ry, x=rx, weights=None, mode=None):
    return BUILTIN.resolve(label)(Sample(y, weights, mode, ref=x))


def test_corr_cov_rcorr():
    assert cross("corr") == pytest.approx(sps.pearsonr(rx, ry)[0])
    assert cross("cov") == pytest.approx(np.cov(rx, ry)[0, 1])
    assert cross("rcorr") == pytest.approx(sps.spearmanr(rx, ry)[0])


def test_unweighted_fit():
    res = sps.linregress(rx, ry)
    assert cross("slope") == pytest.approx(res.slope)
    assert cross("intercept") == pytest.approx(res.intercept)
    assert cross("slope_err") == pytest.approx(res.stderr)
    assert cross("intercept_err") == pytest.approx(res.intercept_stderr)
    assert cross("r2") == pytest.approx(res.rvalue**2)
    resid = ry - (res.intercept + res.slope * rx)
    assert cross("rmsres") == pytest.approx(np.sqrt(np.mean(resid**2)))


def test_error_weighted_fit():
    w = 1 / rsig**2
    (b, a), cov = np.polyfit(rx, ry, 1, w=1 / rsig, cov="unscaled")
    assert cross("slope", weights=w, mode="err") == pytest.approx(b)
    assert cross("intercept", weights=w, mode="err") == pytest.approx(a)
    assert cross("slope_err", weights=w, mode="err") == pytest.approx(np.sqrt(cov[0, 0]))
    assert cross("intercept_err", weights=w, mode="err") == pytest.approx(np.sqrt(cov[1, 1]))
    chi2 = np.sum(((ry - a - b * rx) / rsig) ** 2)
    assert cross("chi2fit", weights=w, mode="err") == pytest.approx(chi2)
    assert cross("rchi2fit", weights=w, mode="err") == pytest.approx(chi2 / (rx.size - 2))


def test_cross_skips_rows_missing_in_either_column():
    y = ry.copy()
    y[3] = np.nan
    x = rx.copy()
    x[7] = np.nan
    keep = ~(np.isnan(x) | np.isnan(y))
    assert cross("corr", y, x) == pytest.approx(sps.pearsonr(x[keep], y[keep])[0])


def test_cross_too_few_points():
    assert np.isnan(cross("corr", np.array([1.0]), np.array([2.0])))
    assert np.isnan(cross("slope_err", np.array([1.0, 2.0]), np.array([0.0, 1.0])))


# -- weights -------------------------------------------------------------------

WX = np.array([3.0, -1.0, 2.5, 8.0, 0.0, 2.5])
WW = np.array([2.0, 1.0, 3.0, 1.0, 4.0, 2.0])
REPLICATED = np.repeat(WX, WW.astype(int))
FREQ_STATS = [s.name for s in BUILTIN if "freq" in s.modes and not s.cross and not s.param]


@pytest.mark.parametrize("label", FREQ_STATS + ["q10", "q62.5", "mom3", "dev2", "ndev3", "absm1.5"])
def test_frequency_weights_equal_replication(label):
    if label in ("nrows",):  # counts rows, not weight
        return
    got = BUILTIN.resolve(label)(Sample(WX, WW, "freq"))
    want = calc(label, REPLICATED)
    if isinstance(want, str):
        assert got == want
    else:
        np.testing.assert_allclose(got, want, rtol=1e-10)


@pytest.mark.parametrize("label", ["corr", "cov", "slope", "intercept", "slope_err", "r2"])
def test_frequency_weighted_cross_equal_replication(label):
    y = np.array([1.0, 2.5, 2.0, 4.0, 6.0, 5.0])
    got = cross(label, y, WX, WW, "freq")
    want = cross(label, np.repeat(y, WW.astype(int)), REPLICATED)
    assert got == pytest.approx(want)


def test_error_weighted_mean():
    sigma = np.array([1.0, 2.0, 0.5])
    x = np.array([10.0, 12.0, 11.0])
    s = Sample(x, 1 / sigma**2, "err")
    w = 1 / sigma**2
    mean = np.sum(w * x) / w.sum()
    assert BUILTIN.resolve("mean")(s) == pytest.approx(mean)
    assert BUILTIN.resolve("stderr")(s) == pytest.approx(1 / np.sqrt(w.sum()))
    chi2 = np.sum(w * (x - mean) ** 2)
    assert BUILTIN.resolve("chi2")(s) == pytest.approx(chi2)
    assert BUILTIN.resolve("rchi2")(s) == pytest.approx(chi2 / 2)


def test_zero_weight_rows_are_dropped():
    s = Sample(np.array([1.0, 100.0]), np.array([1.0, 0.0]), "freq")
    assert BUILTIN.resolve("max")(s) == 1.0


def test_every_stat_has_a_test():
    tested = {BUILTIN.resolve(k).stat.name for k in REFERENCE}
    tested |= {"corr", "cov", "rcorr", "slope", "intercept", "slope_err", "intercept_err"}
    tested |= {"r2", "rmsres", "chi2fit", "rchi2fit", "chi2", "rchi2", "spark"}
    assert tested == {s.name for s in BUILTIN}


def test_nnan():
    assert calc("nnan", np.array([1.0, np.nan, np.nan])) == 2
    assert calc("nnan", np.array([np.nan])) == 1


def test_nan_values_are_skipped():
    assert calc("n", [1.0, np.nan, 3.0]) == 2
    assert calc("mean", [1.0, np.nan, 3.0]) == 2.0


@pytest.mark.parametrize(
    "label,expected", [("n", 0), ("sum", 0), ("mean", np.nan), ("min", np.nan)]
)
def test_empty_column(label, expected):
    np.testing.assert_equal(calc(label, np.array([np.nan])), expected)


def test_small_samples_give_nan_not_errors():
    assert np.isnan(calc("stdev", [1.0]))
    assert np.isnan(calc("skew", [1.0, 2.0]))
    assert np.isnan(calc("kurt", [1.0, 2.0, 3.0]))


def test_constant_data():
    x = np.full(10, 2.0)
    assert calc("skew", x) == 0 and calc("kurt", x) == 0 and calc("stdev", x) == 0


@pytest.mark.parametrize("bad", ["bogus", "qN", "q101", "mean2", "xyz3"])
def test_bad_names(bad):
    with pytest.raises(ValueError):
        BUILTIN.resolve(bad)


def test_spark():
    assert calc("spark", np.arange(100.0)) == "█" * 10
    line = calc("spark4", np.array([0.0, 0, 0, 0, 3, 3]))
    assert line == "█  ▄"  # empty bins are blank
    assert calc("spark", np.array([np.nan])) == ""
