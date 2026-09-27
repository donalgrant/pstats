"""``findgen``: print a sequence of indices, one per line.

Named after IDL's FINDGEN. ``findgen N`` prints 0 .. N-1; handy for adding
an index column with ``paste`` or generating test input for ``stats``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="findgen",
        description="Print N indices, one per line: offset, offset+step, ...",
        epilog="examples:\n  findgen 5            # 0 1 2 3 4\n"
        "  findgen -o 1 -r 3    # 3 2 1\n"
        "  findgen 100 | paste - data.txt | stats mean",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("N", type=int, help="number of indices to generate")
    p.add_argument("-o", "--offset", type=int, default=0, help="first index (default 0)")
    p.add_argument("-s", "--step", type=int, default=1, help="increment (default 1)")
    p.add_argument("-r", "--reverse", action="store_true", help="count down instead of up")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.step == 0:
        parser.error("--step must be non-zero")
    seq = range(args.offset, args.offset + max(args.N, 0) * args.step, args.step)
    if args.reverse:
        seq = seq[::-1]
    chunk = 65536
    for start in range(0, len(seq), chunk):
        sys.stdout.write("".join(f"{i}\n" for i in seq[start : start + chunk]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
