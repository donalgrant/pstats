import numpy as np
import pytest

from stats_cli import analysis
from stats_cli.stats import BUILTIN


def test_groups_sorted_numerically_when_possible():
    keys = np.array(["10", "9", "10", "", "2"])
    got = analysis.groups(keys)
    assert [k for k, _ in got] == ["2", "9", "10"]
    assert got[2][1].tolist() == [0, 2]


def test_groups_text_keys():
    assert [k for k, _ in analysis.groups(np.array(["V", "B", "R", "B"]))] == ["B", "R", "V"]


def test_no_keys_is_one_group():
    assert analysis.groups(None) == [(None, slice(None))]


@pytest.mark.parametrize("text,expected", [("10", 10), ("auto", "auto"), ("fd", "fd")])
def test_parse_bins(text, expected):
    assert analysis.parse_bins(text) == expected


@pytest.mark.parametrize("text", ["0", "-3", "many"])
def test_parse_bins_errors(text):
    with pytest.raises(ValueError):
        analysis.parse_bins(text)


def test_parse_range():
    assert analysis.parse_range("-1:2.5") == (-1.0, 2.5)
    for bad in ["1", "2:1", "a:b"]:
        with pytest.raises(ValueError):
            analysis.parse_range(bad)


def test_histogram_weights_and_nans():
    x = np.array([0.1, 0.2, 0.9, np.nan])
    edges = analysis.bin_edges(x, 2)
    assert analysis.histogram(x, edges).tolist() == [2, 1]
    assert analysis.histogram(x, edges, np.array([1, 3, 2, 5.0])).tolist() == [4, 2]


def boot(label, x, seed=1, level=95, n=500, **kw):
    req = [BUILTIN.resolve(label)]
    return analysis.bootstrap(req, x, kw.get("w"), kw.get("mode"), kw.get("ref"), level, n, seed)[0]


def test_bootstrap_is_reproducible_and_brackets_estimate():
    x = np.random.default_rng(0).normal(10, 2, 200)
    lo, hi = boot("mean", x)
    assert (lo, hi) == boot("mean", x)
    assert lo < x.mean() < hi
    # close to the normal-theory interval mean +- 1.96 s/sqrt(n)
    half = 1.96 * x.std(ddof=1) / np.sqrt(x.size)
    assert (hi - lo) / 2 == pytest.approx(half, rel=0.15)


def test_bootstrap_level_widens_interval():
    x = np.random.default_rng(1).exponential(1, 100)
    lo90, hi90 = boot("median", x, level=90)
    lo99, hi99 = boot("median", x, level=99)
    assert lo99 <= lo90 and hi99 >= hi90


def test_bootstrap_cross_stat_resamples_pairs():
    r = np.random.default_rng(2)
    x = np.arange(50.0)
    y = 2 * x + r.normal(0, 1, 50)
    lo, hi = boot("slope", y, ref=x)
    assert lo < 2 < hi


def test_bootstrap_empty():
    lo, hi = boot("mean", np.array([]))
    assert np.isnan(lo) and np.isnan(hi)


def test_bootstrap_ignores_missing_rows():
    x = np.array([1.0, np.nan, 2.0, np.nan, 3.0, np.nan])
    assert boot("n", x) == (3, 3)  # every resample has the 3 usable rows
    lo, hi = boot("mean", x)
    assert 1 <= lo <= 2 <= hi <= 3


def test_bootstrap_cross_uses_pairs_plain_uses_values():
    x = np.array([0.0, 1, 2, 3, np.nan, 5, 6, 7])
    y = np.array([0.0, 2, 4, 6, 8, np.nan, 12, 14])
    reqs = [BUILTIN.resolve("n"), BUILTIN.resolve("slope")]
    (n_ci, slope_ci) = analysis.bootstrap(reqs, y, None, None, x, 95, 200, 1)
    assert n_ci == (7, 7)  # the plain stat keeps the row whose reference is missing
    assert slope_ci == pytest.approx((2, 2))
