# Changelog

## Unreleased

**Input.**
- `-f FILE` reads from files. It can be repeated to concatenate files, and
  `-` means stdin.
- Delimited input with `-d CHAR`, or the `--csv` and `--tsv` shorthands.
  Empty fields count as missing.
- A first line with no numeric fields is taken as the column names. Override
  this with `--header` or `--no-header-row`.
- `-c SPEC` selects columns: 1-based numbers, ranges such as `2-4` and `3-`,
  or header names.
- `--strict` makes missing or NaN values an error.

**Output.**
- `-F table|csv|tsv|json` chooses the output format.
- `-T` transposes the output, giving one row per statistic.
- `-p` sets the number of significant digits, and `--fmt` accepts a
  printf-style format.
- Rows are labeled automatically when the input has names or `-c` is used.
  Use `-L` or `--no-labels` to override.

**Changed.**
- Table columns now widen to fit long values instead of losing alignment.
- Statistic names and options can be given in any order.

## 0.2.0 (unreleased)

The original `pstats.py` and `findgen.py` scripts have been rewritten as an
installable package, `stats-cli`, which provides the commands `stats` and
`findgen`.

**Compatibility.** Output is identical to the original's for every statistic
it could compute. The only difference is that lines no longer end with a
trailing space.

**Fixes.**
- `absdev` and `absmN` crashed, because a function was missing its `return`.
  Both now work.
- Errors and verbose output now go to stderr, and the exit status is nonzero
  on failure.
- Running with no statistics, non-numeric input, or empty input now gives a
  clear error message instead of a traceback or blank output.
- Removed the `SyntaxWarning`s that Python 3.12+ printed.

**Performance.** numpy replaces pandas.
- About 8× faster on large inputs: 10M values take 1.25 s instead of 9.9 s.
- About 3× faster to start: 0.08 s instead of 0.26 s.
- Columns are no longer sorted once per requested statistic.

**New.**
- `--list-stats` now shows a description of each statistic. It also answers to
  `-l`, and `--stat_list` still works.
- Added `--version`.
- `-q` now suppresses warnings.
- Comments (`#`) and blank lines in the input are ignored.
- NaN-like tokens count as missing values, and short rows are padded with
  missing values.
- `findgen` has a new `--step` option.
- `--no-sort` is accepted but does nothing, since no statistic needs sorted
  data.
