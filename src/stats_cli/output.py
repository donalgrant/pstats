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
    ascii: bool = False  # draw sparklines with ASCII characters


_TO_ASCII = str.maketrans("▁▂▃▄▅▆▇█", ".:-=+*#@")


def _exact(v: float) -> str:
    """Shortest round-trip representation, with integral values as integers."""
    v = float(v)  # int.is_integer() only exists from Python 3.12
    if math.isfinite(v) and v.is_integer() and abs(v) < 2**53:
        return str(int(v))
    return repr(v)


def _formatter(opts: OutputOptions, default_digits: int | None):
    if opts.printf:
        num = lambda v: opts.printf % v  # noqa: E731
    elif (digits := opts.precision or default_digits) is None:
        num = _exact
    else:
        num = lambda v: f"{v:.{digits}g}"  # noqa: E731
    if opts.ascii:
        return lambda v: v.translate(_TO_ASCII) if isinstance(v, str) else num(v)
    return lambda v: v if isinstance(v, str) else num(v)  # text stats (spark) pass through


def render(
    stat_labels: Sequence[str],
    row_labels: Sequence[str | Sequence[str]],
    values: Sequence[Sequence[float | str]],
    opts: OutputOptions,
    label_titles: Sequence[str] = ("column",),
) -> str:
    """Render ``values[row][stat]`` according to ``opts``.

    Each row label is a string or a tuple of strings (e.g. group and column),
    with one title per label part in ``label_titles``.
    """
    row_labels = [(lab,) if isinstance(lab, str) else tuple(lab) for lab in row_labels]
    if opts.format == "json":
        if opts.transpose:  # one record per statistic, keyed by column label
            keys = [":".join(lab) for lab in row_labels]
            columns = list(zip(*values, strict=True)) if values else [()] * len(stat_labels)
            return _json(keys, [(s,) for s in stat_labels], ("stat",), columns, opts.ascii)
        return _json(stat_labels, row_labels, label_titles, values, opts.ascii)

    fmt = _formatter(opts, 4 if opts.format == "table" else None)
    cells = [[fmt(v) for v in row] for row in values]
    head, stub, stub_titles = list(stat_labels), [list(lab) for lab in row_labels], label_titles
    if opts.transpose:
        cells = [list(r) for r in zip(*cells, strict=True)] if cells else []
        head = [":".join(lab) for lab in row_labels]
        stub, stub_titles = [[s] for s in stat_labels], ("stat",)
    # transposed output always needs its stub column (the stat names)
    show_stub = opts.labels or opts.transpose
    show_head = opts.header and (not opts.transpose or opts.labels)

    rows = []
    if show_head:
        rows.append((list(stub_titles) if show_stub else []) + head)
    rows += [(s if show_stub else []) + r for s, r in zip(stub, cells, strict=True)]
    nstub = len(stub_titles) if show_stub else 0

    if opts.format in ("csv", "tsv"):
        buf = io.StringIO()
        delim = "," if opts.format == "csv" else "\t"
        csv.writer(buf, delimiter=delim, lineterminator="\n").writerows(rows)
        return buf.getvalue().rstrip("\n")
    return _table(rows, nstub)


def _table(rows: list[list[str]], nstub: int) -> str:
    if not rows:
        return ""
    ncols = len(rows[0])
    widths = [max(len(r[i]) for r in rows) for i in range(ncols)]
    lines = []
    for r in rows:
        parts = []
        for i, cell in enumerate(r):
            if i < nstub:
                parts.append(cell.ljust(widths[i]))
            else:
                parts.append(cell.rjust(max(MIN_WIDTH, widths[i])))
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _json(stat_labels, row_labels, label_titles, values, ascii=False) -> str:
    def clean(v):
        if isinstance(v, str):
            return v.translate(_TO_ASCII) if ascii else v
        v = float(v)
        if not math.isfinite(v):
            return None
        return int(v) if v.is_integer() and abs(v) < 2**53 else v

    records = [
        {
            **dict(zip(label_titles, lab, strict=True)),
            **{s: clean(v) for s, v in zip(stat_labels, row, strict=True)},
        }
        for lab, row in zip(row_labels, values, strict=True)
    ]
    return json.dumps(records, indent=2)


_EIGHTHS = " ▏▎▍▌▋▊▉█"


def bar(value: float, scale: float, width: int, ascii: bool = False) -> str:
    """A horizontal bar of ``value / scale * width`` characters (eighth-block resolution)."""
    if scale <= 0 or not math.isfinite(value) or value <= 0:
        return ""
    length = value / scale * width
    if ascii:
        return "#" * max(1, round(length))
    full, part = divmod(round(length * 8), 8)
    text = "█" * full + (_EIGHTHS[part] if part else "")
    return text or "▏"  # never hide a non-empty bin


def render_hist(
    blocks: Sequence[tuple[Sequence[str], Sequence[float], Sequence[float]]],
    opts: OutputOptions,
    label_titles: Sequence[str] = ("column",),
    bar_width: int = 40,
    ascii: bool = False,
) -> str:
    """Render histograms: ``blocks`` holds (label parts, bin edges, counts) per histogram."""
    records = [
        (tuple(lab), edges[i], edges[i + 1], c)
        for lab, edges, counts in blocks
        for i, c in enumerate(counts)
    ]
    if opts.format == "json":
        return json.dumps(
            [
                {**dict(zip(label_titles, lab, strict=True)), "lo": lo, "hi": hi, "count": _num(c)}
                for lab, lo, hi, c in records
            ],
            indent=2,
        )
    fmt = _formatter(opts, 4 if opts.format == "table" else None)
    count = lambda c: _exact(c) if float(c).is_integer() else fmt(c)  # noqa: E731
    if opts.format in ("csv", "tsv"):
        rows = [[*label_titles, "lo", "hi", "count"]] if opts.header else []
        rows += [[*lab, fmt(lo), fmt(hi), count(c)] for lab, lo, hi, c in records]
        buf = io.StringIO()
        delim = "," if opts.format == "csv" else "\t"
        csv.writer(buf, delimiter=delim, lineterminator="\n").writerows(rows)
        return buf.getvalue().rstrip("\n")

    out = []
    for lab, edges, counts in blocks:
        title = []
        if len(blocks) > 1 or opts.labels:
            title = ["  ".join(f"{t}: {v}" for t, v in zip(label_titles, lab, strict=True))]
        rows = [["lo", "hi", "count"]] if opts.header else []
        rows += [[fmt(edges[i]), fmt(edges[i + 1]), count(c)] for i, c in enumerate(counts)]
        lines = _table(rows, 0).splitlines()
        top = max(counts, default=0)
        start = 1 if opts.header else 0
        for k, c in enumerate(counts, start):
            lines[k] = f"{lines[k]}  {bar(c, top, bar_width, ascii)}".rstrip()
        out.append("\n".join(title + lines))
    return "\n\n".join(out)


def _num(v: float):
    return int(v) if float(v).is_integer() else float(v)
