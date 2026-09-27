"""Grouping, histograms and bootstrap confidence intervals."""

from __future__ import annotations

import warnings
from collections.abc import Sequence

import numpy as np

from .registry import Request, Sample

BIN_RULES = ("auto", "fd", "doane", "scott", "stone", "rice", "sturges", "sqrt")


def _sort_key(keys: Sequence[str]):
    try:
        [float(k) for k in keys]
    except ValueError:
        return None  # text keys: plain string order
    return float


def groups(keys: np.ndarray | None) -> list[tuple[str | None, np.ndarray]]:
    """(key, row indices) for each group, sorted (numerically if every key is a number).

    Without keys there is one group, ``None``, holding every row. Rows with an
    empty key are left out.
    """
    if keys is None:
        return [(None, slice(None))]
    present = keys != ""
    unique = sorted(set(keys[present].tolist()), key=_sort_key(keys[present].tolist()))
    return [(k, np.flatnonzero(keys == k)) for k in unique]


def parse_bins(text: str) -> int | str:
    if text.isdigit() and int(text) > 0:
        return int(text)
    if text in BIN_RULES:
        return text
    raise ValueError(f"--bins must be a positive integer or one of {', '.join(BIN_RULES)}")


def parse_range(text: str) -> tuple[float, float]:
    lo, sep, hi = text.partition(":")
    try:
        bounds = (float(lo), float(hi))
    except ValueError:
        bounds = None
    if not sep or bounds is None or bounds[0] >= bounds[1]:
        raise ValueError("--range must be LO:HI with LO < HI, e.g. 0:100")
    return bounds


def bin_edges(x: np.ndarray, bins: int | str, value_range=None) -> np.ndarray:
    x = x[~np.isnan(x)]
    return np.histogram_bin_edges(x, bins=bins, range=value_range)


def histogram(x: np.ndarray, edges: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    valid = ~np.isnan(x)
    if weights is not None:
        valid &= ~np.isnan(weights)
    w = weights[valid] if weights is not None else None
    counts, _ = np.histogram(x[valid], bins=edges, weights=w)
    return counts


def _usable(values, weights, ref) -> np.ndarray:
    ok = ~np.isnan(values)
    if weights is not None:
        ok &= ~np.isnan(weights) & (weights > 0)
    if ref is not None:
        ok &= ~np.isnan(ref)
    return ok


def bootstrap(
    requests: Sequence[Request],
    values: np.ndarray,
    weights: np.ndarray | None,
    mode: str | None,
    ref: np.ndarray | None,
    level: float,
    resamples: int,
    seed,
) -> list[tuple[float, float]]:
    """Percentile-bootstrap confidence intervals for each (numeric) request.

    Only usable rows are resampled: rows with a value (and a valid weight),
    and for statistics against the reference column (-x) also a reference
    value, so every resample has the same size as the data behind the
    estimate. Each row keeps its weight and reference value. The interval is
    the central ``level`` percent of the resampled statistic; the same
    ``seed`` gives the same resamples.
    """
    out: list[tuple[float, float] | None] = [None] * len(requests)
    for cross in (False, True):
        which = [k for k, r in enumerate(requests) if r.stat.cross == cross]
        if not which:
            continue
        r_ref = ref if cross else None
        ok = _usable(values, weights, r_ref)
        intervals = _bootstrap_rows(
            [requests[k] for k in which],
            values[ok],
            weights[ok] if weights is not None else None,
            mode,
            r_ref[ok] if r_ref is not None else None,
            level,
            resamples,
            seed,
        )
        for k, ci in zip(which, intervals, strict=True):
            out[k] = ci
    return out


def _bootstrap_rows(requests, values, weights, mode, ref, level, resamples, seed):
    rng = np.random.default_rng(seed)
    m = values.size
    if m == 0:
        return [(np.nan, np.nan)] * len(requests)
    results = np.full((resamples, len(requests)), np.nan)
    for b in range(resamples):
        i = rng.integers(0, m, m)
        s = Sample(
            values[i],
            weights[i] if weights is not None else None,
            mode,
            ref=ref[i] if ref is not None else None,
        )
        results[b] = [r(s) for r in requests]
    tail = (100 - level) / 2
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN statistics
        lo = np.nanpercentile(results, tail, axis=0)
        hi = np.nanpercentile(results, 100 - tail, axis=0)
    return list(zip(lo.tolist(), hi.tolist(), strict=True))
