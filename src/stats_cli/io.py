"""Reading whitespace-delimited numeric columns."""

from __future__ import annotations

import io
import warnings
from collections.abc import Callable

import numpy as np

_NAN_TOKENS = {"nan", "na", "n/a", "null", "none", "-"}


class DataError(ValueError):
    pass


def read_columns(text: str, warn: Callable[[str], None] = lambda msg: None) -> np.ndarray:
    """Parse ``text`` into a 2-D float array, one column per input field.

    Blank lines and ``#`` comments are ignored. Rows shorter than the widest
    row are padded with NaN (with a warning); NaN-like tokens (``nan``,
    ``NA``, ...) become NaN. Any other non-numeric token raises DataError.
    """
    try:
        # numpy's C parser: fast for the common rectangular, all-numeric case
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # "input contained no data"
            data = np.loadtxt(io.StringIO(text), dtype=float, ndmin=2, comments="#")
    except ValueError:
        data = _read_slow(text, warn)
    if data.size == 0:
        raise DataError("no input data")
    return data


def _read_slow(text: str, warn: Callable[[str], None]) -> np.ndarray:
    rows: list[list[float]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        row = []
        for tok in fields:
            try:
                row.append(float(tok))
            except ValueError:
                if tok.lower() in _NAN_TOKENS:
                    row.append(np.nan)
                else:
                    raise DataError(f"line {lineno}: non-numeric value {tok!r}") from None
        rows.append(row)
    width = max(map(len, rows), default=0)
    short = sum(len(r) < width for r in rows)
    if short:
        warn(f"{short} row(s) have fewer than {width} fields; missing values ignored")
    out = np.full((len(rows), width), np.nan)
    for i, r in enumerate(rows):
        out[i, : len(r)] = r
    return out
