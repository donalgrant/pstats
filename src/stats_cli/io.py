"""Reading delimited numeric columns, with optional header rows and column selection."""

from __future__ import annotations

import io
import sys
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

_NAN_TOKENS = {"", "nan", "na", "n/a", "null", "none", "-"}

Warn = Callable[[str], None]


def _no_warn(msg: str) -> None:
    pass


class DataError(ValueError):
    pass


@dataclass
class Table:
    """Parsed input: ``data`` is rows x columns; ``labels`` names each column.

    ``named`` is true when the labels came from a header row (otherwise they
    are the 1-based column numbers).
    """

    data: np.ndarray
    labels: list[str]
    named: bool = False


@dataclass
class ReadOptions:
    delimiter: str | None = None  # None: any run of whitespace
    header: str = "auto"  # "auto", "yes" or "no"
    columns: str | None = None  # a -c spec, e.g. "1,3-5" or "height,weight"
    strict: bool = False


def _split(line: str, delimiter: str | None) -> list[str]:
    line = line.split("#", 1)[0]
    if delimiter is None:
        return line.split()
    if not line.strip():
        return []
    return [f.strip() for f in line.split(delimiter)]


def _is_number(tok: str) -> bool:
    try:
        float(tok)
    except ValueError:
        return False
    return True


def _first_row(text: str, delimiter: str | None) -> tuple[int, int, list[str]] | None:
    """Start offset, end offset and fields of the first non-blank, non-comment line."""
    pos = 0
    while pos < len(text):
        end = text.find("\n", pos)
        end = len(text) if end == -1 else end + 1
        fields = _split(text[pos:end], delimiter)
        if fields:
            return pos, end, fields
        pos = end
    return None


def parse_columns(spec: str, names: Sequence[str] | None, width: int) -> list[int]:
    """Resolve a -c spec to 0-based column indices, in the order given.

    Items are comma-separated: a 1-based number (``3``), a range (``2-4``),
    an open range (``3-``, to the last column) or a header name.
    """
    out: list[int] = []
    for item in (s.strip() for s in spec.split(",")):
        if names and item in names:
            out.append(list(names).index(item))
            continue
        lo, sep, hi = item.partition("-")
        try:
            first = int(lo)
            last = (int(hi) if hi else width) if sep else first
        except ValueError:
            known = f" (columns: {', '.join(names)})" if names else ""
            raise DataError(f"unknown column {item!r}{known}") from None
        if first < 1 or last < first or last > width:
            raise DataError(f"column {item!r} out of range (input has {width} columns)")
        out.extend(range(first - 1, last))
    return out


def read_table(text: str, opts: ReadOptions | None = None, warn: Warn = _no_warn) -> Table:
    """Parse ``text`` into a :class:`Table`.

    Blank lines and ``#`` comments are ignored. With ``header="auto"`` a
    first line containing no numeric fields supplies the column names.
    NaN-like tokens (``nan``, ``NA``, empty delimited fields) and fields
    missing from short rows become NaN, unless ``strict`` is set, in which
    case they are errors. Any other non-numeric token raises DataError.
    """
    opts = opts or ReadOptions()
    first = _first_row(text, opts.delimiter)
    if first is None:
        raise DataError("no input data")
    row_start, row_end, fields = first

    has_header = opts.header == "yes" or (
        opts.header == "auto" and not any(map(_is_number, fields))
    )
    names = fields if has_header else None
    body = text[row_end:] if has_header else text[row_start:]
    first_lineno = text.count("\n", 0, row_end if has_header else row_start) + 1
    width = len(fields)

    cols = parse_columns(opts.columns, names, width) if opts.columns else None
    data = _parse_body(body, first_lineno, opts, cols, warn)
    if data.shape[0] == 0:
        raise DataError("no input data" + (" after the header row" if has_header else ""))
    if opts.strict and np.isnan(data).any():
        raise DataError("missing or NaN values present (--strict)")

    idx = cols if cols is not None else range(data.shape[1])
    if names:
        labels = [names[i] if i < len(names) else str(i + 1) for i in idx]
    else:
        labels = [str(i + 1) for i in idx]
    return Table(data, labels, named=bool(names))


def _parse_body(
    body: str, first_lineno: int, opts: ReadOptions, cols: list[int] | None, warn: Warn
) -> np.ndarray:
    try:
        # numpy's C parser: fast for the common rectangular, all-numeric case
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # "input contained no data"
            return np.loadtxt(
                io.StringIO(body),
                dtype=float,
                ndmin=2,
                comments="#",
                delimiter=opts.delimiter,
                usecols=cols,
            )
    except ValueError:
        return _parse_slow(body, first_lineno, opts, cols, warn)


def _parse_slow(
    body: str, first_lineno: int, opts: ReadOptions, cols: list[int] | None, warn: Warn
) -> np.ndarray:
    rows: list[list[float]] = []
    for lineno, line in enumerate(body.splitlines(), first_lineno):
        fields = _split(line, opts.delimiter)
        if not fields:
            continue
        row = []
        for tok in fields:
            try:
                row.append(float(tok))
            except ValueError:
                if tok.lower() not in _NAN_TOKENS:
                    raise DataError(f"line {lineno}: non-numeric value {tok!r}") from None
                if opts.strict:
                    raise DataError(f"line {lineno}: missing value {tok!r} (--strict)") from None
                row.append(np.nan)
        rows.append(row)
    width = max(map(len, rows), default=0)
    short = sum(len(r) < width for r in rows)
    if short:
        if opts.strict:
            raise DataError(f"{short} row(s) have fewer than {width} fields (--strict)")
        warn(f"{short} row(s) have fewer than {width} fields; missing values ignored")
    out = np.full((len(rows), width), np.nan)
    for i, r in enumerate(rows):
        out[i, : len(r)] = r
    if cols is not None:
        if any(c >= width for c in cols):
            raise DataError(f"column out of range (input has {width} columns)")
        out = out[:, cols]
    return out


def read_sources(paths: Sequence[str], opts: ReadOptions, warn: Warn = _no_warn) -> Table:
    """Read and concatenate the rows of several inputs (``-`` is stdin)."""
    tables = []
    for path in paths or ["-"]:
        try:
            if path == "-":
                text = sys.stdin.read()
            else:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
        except OSError as e:
            raise DataError(f"{path}: {e.strerror}") from None
        try:
            tables.append(read_table(text, opts, warn))
        except DataError as e:
            raise DataError(f"{path}: {e}" if len(paths) > 1 or path != "-" else str(e)) from None
    return concat(tables, warn)


def concat(tables: Sequence[Table], warn: Warn = _no_warn) -> Table:
    """Stack tables row-wise, padding narrower ones with NaN."""
    if len(tables) == 1:
        return tables[0]
    width = max(t.data.shape[1] for t in tables)
    if any(t.data.shape[1] != width for t in tables):
        warn(f"inputs have different numbers of columns; padded to {width}")
    parts = []
    for t in tables:
        pad = np.full((t.data.shape[0], width - t.data.shape[1]), np.nan)
        parts.append(np.hstack([t.data, pad]))
    named = [t for t in tables if t.named]
    if any(t.labels != named[0].labels for t in named[1:]):
        warn("inputs have different header names; using the first")
    base = (named[0] if named else max(tables, key=lambda t: len(t.labels))).labels
    labels = base + [str(i + 1) for i in range(len(base), width)]
    return Table(np.vstack(parts), labels[:width], named=bool(named))
