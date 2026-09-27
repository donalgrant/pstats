"""Command-line interface for ``stats``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .io import DataError, ReadOptions, read_sources
from .output import FORMATS, OutputOptions, render
from .registry import ERR, FREQ, NONE, Registry, Sample, UnknownStatError
from .stats import BUILTIN

EXIT_OK, EXIT_DATA, EXIT_USAGE = 0, 1, 2
MATRIX_STATS = ("corr", "cov", "rcorr")

DESCRIPTION = """\
Compute statistics of numeric columns read from stdin or files.

Each named statistic is computed for every input column; the output has one
row per input column and one field per statistic, in the order requested.
Parameterized statistics take a number in place of N: q25 is the 25th
percentile, mom3 the third raw moment. Use --list-stats to see them all."""

EPILOG = """\
examples:
  seq 1 100 | stats n mean stdev
  stats min q25 median q75 max < data.txt
  stats -nh mean < data.txt              # no header line
  paste x.txt y.txt | stats n mean rms   # one output row per column
  stats --csv -f data.csv -c height,weight mean stdev
  stats -f a.txt -f b.txt -c 2- median   # rows of both files; columns 2 onward
  seq 100 | stats -T n mean stdev        # one statistic per line
  stats -F json mean q90 < data.txt
  stats -x 1 corr slope slope_err r2 < xy.txt   # compare each column with column 1
  stats -e 2 mean stderr rchi2 < values.txt     # inverse-variance weighted mean
  stats --matrix corr < data.txt

input:
  Fields are separated by whitespace unless -d/--csv/--tsv is given. Blank
  lines and text after '#' are ignored. A first line with no numeric fields
  is taken as column names (see --header). NaN-like tokens (nan, NA), empty
  delimited fields and missing trailing fields are skipped when computing
  statistics, unless --strict is given.

output:
  Rows are labelled with their column name or number when the input has a
  header row or -c is used (force with -L, suppress with --no-labels)."""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stats",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("stats", metavar="STAT", nargs="*", help="statistics to compute")
    p.add_argument(
        "-l",
        "--list-stats",
        "--stat_list",
        action="store_true",
        help="list the available statistics and exit",
    )

    inp = p.add_argument_group("input options")
    inp.add_argument(
        "-f",
        "--file",
        action="append",
        default=[],
        metavar="FILE",
        help="read FILE instead of stdin ('-' is stdin); repeat to concatenate files",
    )
    delim = inp.add_mutually_exclusive_group()
    delim.add_argument("-d", "--delimiter", metavar="CHAR", help="field delimiter (e.g. ',')")
    delim.add_argument(
        "--csv",
        action="store_const",
        dest="delimiter",
        const=",",
        help="comma-delimited input (same as -d ,)",
    )
    delim.add_argument(
        "--tsv", action="store_const", dest="delimiter", const="\t", help="tab-delimited input"
    )
    head = inp.add_mutually_exclusive_group()
    head.add_argument(
        "--header",
        action="store_const",
        dest="header_row",
        const="yes",
        help="treat the first line as column names",
    )
    head.add_argument(
        "--no-header-row",
        action="store_const",
        dest="header_row",
        const="no",
        help="never treat the first line as column names",
    )
    inp.add_argument(
        "-c",
        "--columns",
        metavar="SPEC",
        help="columns to use, by 1-based number, range or name: 2,4-6,9- or height,weight",
    )
    inp.add_argument("--strict", action="store_true", help="make missing or NaN values an error")

    rel = p.add_argument_group("weights and relations between columns")
    rel.add_argument(
        "-x",
        "--ref",
        metavar="COL",
        help="reference column for corr, cov and fit statistics (y = a + b*x); "
        "its own row is omitted",
    )
    weights = rel.add_mutually_exclusive_group()
    weights.add_argument(
        "-w", "--weights", metavar="COL", help="frequency weights: each row counts w times"
    )
    weights.add_argument(
        "-e",
        "--errors",
        metavar="COL",
        help="measurement errors sigma (the same for every data column): "
        "inverse-variance weights 1/sigma**2",
    )
    rel.add_argument(
        "--matrix",
        choices=MATRIX_STATS,
        help="print the matrix of corr, cov or rcorr between all data columns",
    )

    out = p.add_argument_group("output options")
    out.add_argument("-nh", "--no-header", action="store_true", help="omit the header line")
    out.add_argument(
        "-F", "--format", choices=FORMATS, default="table", help="output format (default: table)"
    )
    out.add_argument(
        "-T", "--transpose", action="store_true", help="one row per statistic instead of per column"
    )
    labels = out.add_mutually_exclusive_group()
    labels.add_argument(
        "-L",
        "--labels",
        action="store_true",
        default=None,
        help="always label rows with the column name or number",
    )
    labels.add_argument("--no-labels", action="store_false", dest="labels", help="never label rows")
    out.add_argument(
        "-p",
        "--precision",
        type=int,
        metavar="DIGITS",
        help="significant digits (default: 4 in tables, full in csv/tsv)",
    )
    out.add_argument("--fmt", metavar="PRINTF", help="printf-style number format, e.g. %%.3f")

    verbosity = p.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v", "--verbose", action="store_true", help="report parsing details on stderr"
    )
    verbosity.add_argument("-q", "--quiet", action="store_true", help="suppress warnings")
    p.add_argument("--no-sort", action="store_true", help=argparse.SUPPRESS)  # obsolete
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def list_stats(registry: Registry) -> str:
    stats = list(registry)
    width = max(len(s.display_name) for s in stats)

    def line(s):
        flags = ("w" if FREQ in s.modes else " ") + " " + ("e" if ERR in s.modes else " ")
        return f"  {s.display_name:<{width}}  {flags}  {s.summary}"

    return "\n".join(
        [
            "per-column statistics (w: allowed with -w weights, e: allowed with -e errors):",
            *(line(s) for s in stats if not s.cross),
            "",
            "between each column and the reference column (need -x COL):",
            *(line(s) for s in stats if s.cross),
        ]
    )


def _mode_error(label: str, stat, mode: str | None) -> str:
    if stat.modes == {ERR}:
        return f"{label} requires measurement errors (-e COL)"
    if mode == ERR:
        return f"{label} is not defined with -e (measurement errors); use -w for frequency weights"
    return f"{label} does not support weights (-w)"


def main(argv: Sequence[str] | None = None, registry: Registry = BUILTIN) -> int:
    parser = build_parser()
    args = parser.parse_intermixed_args(argv)

    def warn(msg: str) -> None:
        if not args.quiet:
            print(f"stats: warning: {msg}", file=sys.stderr)

    def info(msg: str) -> None:
        if args.verbose:
            print(f"stats: {msg}", file=sys.stderr)

    def usage_error(msg: str) -> int:
        print(f"stats: error: {msg}", file=sys.stderr)
        return EXIT_USAGE

    if args.list_stats:
        print(list_stats(registry))
        return EXIT_OK
    mode = FREQ if args.weights else ERR if args.errors else NONE
    if args.matrix:
        if args.stats:
            return usage_error("--matrix cannot be combined with statistic names")
        if args.ref:
            return usage_error("--matrix cannot be combined with -x")
        names = [args.matrix]
    elif not args.stats:
        parser.print_usage(sys.stderr)
        return usage_error("no statistics requested (see --list-stats)")
    else:
        names = args.stats
    try:
        requests = [registry.resolve(name) for name in names]
    except UnknownStatError as e:
        return usage_error(f"{e} (see --list-stats)")
    for r in requests:
        if mode not in r.stat.modes:
            return usage_error(_mode_error(r.label, r.stat, mode))
        if r.stat.cross and not (args.ref or args.matrix):
            return usage_error(f"{r.label} needs a reference column (-x COL)")
    if args.fmt:
        try:
            args.fmt % 1.0
        except (TypeError, ValueError):
            return usage_error(f"invalid --fmt {args.fmt!r}; expected e.g. %.3f")
    if args.precision is not None and args.precision < 1:
        return usage_error("--precision must be at least 1")
    if args.delimiter is not None and len(args.delimiter) != 1:
        return usage_error("--delimiter must be a single character")

    read_opts = ReadOptions(
        delimiter=args.delimiter,
        header=args.header_row or "auto",
        columns=args.columns,
        strict=args.strict,
        roles={
            role: spec
            for role, spec in (
                ("ref", args.ref),
                ("weights", args.weights),
                ("errors", args.errors),
            )
            if spec
        },
    )
    try:
        table = read_sources(args.file, read_opts, warn)
        weights = _weights(table.roles, mode)
    except DataError as e:
        print(f"stats: error: {e}", file=sys.stderr)
        return EXIT_DATA
    info(f"read {table.data.shape[0]} rows x {table.data.shape[1]} columns")
    if table.named:
        info(f"column names: {', '.join(table.labels)}")

    ref = table.roles.get("ref")
    columns = list(table.data.T)
    if args.matrix:
        (req,) = requests
        values = [[req(Sample(y, weights, mode, ref=x)) for x in columns] for y in columns]
        stat_labels = table.labels
    else:
        values = []
        for label, col in zip(table.labels, columns, strict=True):
            sample = Sample(col, weights, mode, ref=ref)
            if sample.nrows < col.size:
                info(
                    f"column {label}: skipped {col.size - sample.nrows} row(s) with missing values"
                )
            values.append([r(sample) for r in requests])
        stat_labels = [r.label for r in requests]

    auto_labels = table.named or bool(args.columns or table.roles or args.matrix)
    labels = args.labels if args.labels is not None else auto_labels
    out_opts = OutputOptions(
        format=args.format,
        header=not args.no_header,
        labels=labels,
        transpose=args.transpose,
        precision=args.precision,
        printf=args.fmt,
    )
    text = render(stat_labels, table.labels, values, out_opts)
    if text:
        print(text)
    return EXIT_OK


def _weights(roles, mode):
    """Per-row weights for the Sample: frequency weights, or 1/sigma**2 for -e."""
    if mode == FREQ:
        w = roles["weights"]
        if (w < 0).any():
            raise DataError("weights must not be negative")
        return w
    if mode == ERR:
        sigma = roles["errors"]
        if (sigma <= 0).any():
            raise DataError("errors (-e) must be positive")
        return 1 / sigma**2
    return None


if __name__ == "__main__":
    sys.exit(main())
