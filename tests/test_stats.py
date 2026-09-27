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


@pytest.mark.parametrize("label", REFERENCE)
@pytest.mark.parametrize("i", range(len(DATA)))
def test_against_reference(label, i):
    x = DATA[i]
    assert calc(label, x) == pytest.approx(REFERENCE[label](x), rel=1e-10, abs=1e-12)


def test_every_stat_has_a_reference():
    tested = {BUILTIN.resolve(k).stat.name for k in REFERENCE}
    assert tested == {s.name for s in BUILTIN}


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
