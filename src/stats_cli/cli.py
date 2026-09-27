"""Command-line interface for ``stats``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .io import DataError, read_columns
from .registry import Registry, Sample, UnknownStatError
from .stats import BUILTIN

EXIT_OK, EXIT_DATA, EXIT_USAGE = 0, 1, 2

DESCRIPTION = """\
Compute statistics of whitespace-delimited numeric columns read from stdin.

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

Blank lines and text after '#' are ignored. NaN-like tokens (nan, NA) and
missing trailing fields are skipped when computing statistics."""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stats",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("stats", metavar="STAT", nargs="*", help="statistics to compute")
    p.add_argument("-nh", "--no-header", action="store_true", help="omit the header line")
    p.add_argument(
        "-l",
        "--list-stats",
        "--stat_list",
        action="store_true",
        help="list the available statistics and exit",
    )
    verbosity = p.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="report parsing details on stderr",
    )
    verbosity.add_argument("-q", "--quiet", action="store_true", help="suppress warnings")
    p.add_argument("--no-sort", action="store_true", help=argparse.SUPPRESS)  # obsolete
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def list_stats(registry: Registry) -> str:
    stats = list(registry)
    width = max(len(s.display_name) for s in stats)
    return "\n".join(f"  {s.display_name:<{width}}  {s.summary}" for s in stats)


def main(argv: Sequence[str] | None = None, registry: Registry = BUILTIN) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    def warn(msg: str) -> None:
        if not args.quiet:
            print(f"stats: warning: {msg}", file=sys.stderr)

    def info(msg: str) -> None:
        if args.verbose:
            print(f"stats: {msg}", file=sys.stderr)

    if args.list_stats:
        print(list_stats(registry))
        return EXIT_OK
    if not args.stats:
        parser.print_usage(sys.stderr)
        print("stats: error: no statistics requested (see --list-stats)", file=sys.stderr)
        return EXIT_USAGE
    try:
        requests = [registry.resolve(name) for name in args.stats]
    except UnknownStatError as e:
        print(f"stats: error: {e} (see --list-stats)", file=sys.stderr)
        return EXIT_USAGE

    try:
        data = read_columns(sys.stdin.read(), warn)
    except DataError as e:
        print(f"stats: error: {e}", file=sys.stderr)
        return EXIT_DATA
    info(f"read {data.shape[0]} rows x {data.shape[1]} columns")

    out = []
    if not args.no_header:
        out.append(" ".join(f"{r.label:>10s}" for r in requests))
    for col in data.T:
        sample = Sample(col)
        if sample.n < col.size:
            info(f"column skipped {col.size - sample.n} missing value(s)")
        out.append(" ".join(f"{r(sample):10.4g}" for r in requests))
    print("\n".join(out))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
