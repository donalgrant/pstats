"""Rendering results as an aligned table, CSV/TSV or JSON."""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

FORMATS = ("table", "csv", "tsv", "json")
MIN_WIDTH = 10  # the original pstats field width


@dataclass
class OutputOptions:
    format: str = "table"
    header: bool = True
    labels: bool = False  # lead each row with its column label
    transpose: bool = False  # statistics as rows, columns as fields
    precision: int | None = None  # significant digits
    printf: str | None = None  # e.g. "%.3f"; overrides precision


def _exact(v: float) -> str:
    """Shortest round-trip representation, with integral values as integers."""
    if math.isfinite(v) and v.is_integer() and abs(v) < 2**53:
        return str(int(v))
    return repr(v)


def _formatter(opts: OutputOptions, default_digits: int | None):
    if opts.printf:
        return lambda v: opts.printf % v
    digits = opts.precision or default_digits
    if digits is None:
        return _exact
    return lambda v: f"{v:.{digits}g}"


def render(
    stat_labels: Sequence[str],
    col_labels: Sequence[str],
    values: Sequence[Sequence[float]],
    opts: OutputOptions,
) -> str:
    """Render ``values[column][stat]`` according to ``opts``."""
    if opts.format == "json":
        return _json(stat_labels, col_labels, values)

    fmt = _formatter(opts, 4 if opts.format == "table" else None)
    cells = [[fmt(v) for v in row] for row in values]
    head, stub, stub_title = list(stat_labels), list(col_labels), "column"
    if opts.transpose:
        cells = [list(r) for r in zip(*cells, strict=True)] if cells else []
        head, stub, stub_title = list(col_labels), list(stat_labels), "stat"
    # transposed output always needs its stub column (the stat names)
    show_stub = opts.labels or opts.transpose
    show_head = opts.header and (not opts.transpose or opts.labels)

    rows = []
    if show_head:
        rows.append(([stub_title] if show_stub else []) + head)
    rows += [([s] if show_stub else []) + r for s, r in zip(stub, cells, strict=True)]

    if opts.format in ("csv", "tsv"):
        buf = io.StringIO()
        delim = "," if opts.format == "csv" else "\t"
        csv.writer(buf, delimiter=delim, lineterminator="\n").writerows(rows)
        return buf.getvalue().rstrip("\n")
    return _table(rows, show_stub)


def _table(rows: list[list[str]], stub: bool) -> str:
    if not rows:
        return ""
    ncols = len(rows[0])
    widths = [max(len(r[i]) for r in rows) for i in range(ncols)]
    lines = []
    for r in rows:
        parts = []
        for i, cell in enumerate(r):
            if stub and i == 0:
                parts.append(cell.ljust(widths[0]))
            else:
                parts.append(cell.rjust(max(MIN_WIDTH, widths[i])))
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _json(
    stat_labels: Sequence[str], col_labels: Sequence[str], values: Sequence[Sequence[float]]
) -> str:
    def clean(v: float):
        if not math.isfinite(v):
            return None
        return int(v) if v.is_integer() and abs(v) < 2**53 else v

    records = [
        {"column": c, **{s: clean(v) for s, v in zip(stat_labels, row, strict=True)}}
        for c, row in zip(col_labels, values, strict=True)
    ]
    return json.dumps(records, indent=2)
