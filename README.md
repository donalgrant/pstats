# stats

Column statistics for numeric data, from the command line.

`stats` reads numbers from standard input or files and prints the statistics
you name, one output row per input column. It is a Python/numpy port of an
older C++ tool, designed to sit in Unix pipelines.

```console
$ seq 1 100 | stats n mean stdev q10 q90
         n       mean      stdev        q10        q90
       100       50.5      29.01       10.9       90.1

$ paste <(seq 1 10) <(seq 10 10 100) | stats -nh mean median
       5.5        5.5
        55         55
```

<!-- file: people.csv -->
```text
height,weight,age
170,65,30
182,80,
165,,41
176,71,52
```

```console
$ stats --csv -f people.csv n mean stdev
column          n       mean      stdev
height          4      173.2      7.365
weight          3         72       7.55
age             3         41         11

$ stats --csv -f people.csv -c age -T n mean median
stat          age
n               3
mean           41
median         41
```

The package also installs `findgen`, a small index generator (`findgen 5`
prints 0 through 4).

**[The user guide](https://github.com/donalgrant/stats-cli/blob/main/docs/guide.md)** covers everything with worked examples, from a
first session to fits, weights, groups, histograms and confidence
intervals, plus recipes and a full option reference.

## Install

Requires Python 3.10+. numpy is installed automatically. The package is
published on [PyPI](https://pypi.org/project/stats-cli/) as `stats-cli`, and
is best installed as an isolated command-line tool:

```text
pipx install stats-cli
# or
uv tool install stats-cli
```

Either one installs the `stats` and `findgen` commands. Upgrade later with
`pipx upgrade stats-cli` or `uv tool upgrade stats-cli`. You can also use
`pip install stats-cli` inside a virtual environment.

To install the latest unreleased code from GitHub instead, use
`pipx install git+https://github.com/donalgrant/stats-cli.git`.

To install from a local checkout for development, use
`python -m venv .venv && .venv/bin/pip install -e '.[dev]'`.

## What it does

- **About 50 statistics:** counts, means (arithmetic, geometric, harmonic,
  trimmed), spread (`stdev`, `stderr`, `mad`, `iqr`, ...), any percentile
  (`q2.5`), moments, skewness and kurtosis. `stats -l` lists them all.
- **Input:** whitespace, CSV or TSV; header rows detected automatically;
  columns chosen by number, range or name; missing values skipped (or an
  error with `--strict`).
- **Output:** aligned tables, CSV, TSV or JSON, optionally transposed, with
  the precision you choose.
- **Relations between columns:** correlation, covariance and straight-line
  fits against a reference column (`-x`), and correlation matrices.
- **Weights:** frequency weights (`-w`), or measurement errors (`-e`) for
  inverse-variance means, χ² and weighted fits.
- **Groups** (`-g`), **histograms** (`--hist`) and sparklines, and
  **bootstrap confidence intervals** (`--ci`) for any statistic.

Errors go to stderr. The exit status is 0 on success, 1 for a problem with
the data and 2 for a problem with the command. See the
[user guide](https://github.com/donalgrant/stats-cli/blob/main/docs/guide.md) for all of it.

## Development

```text
.venv/bin/pytest          # tests, including golden-output checks against the original pstats
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

The examples in the README and the user guide run as tests
(`tests/test_docs.py`). After changing them, run the tests to check that the
output shown is still what `stats` prints.

To add a statistic, register a `Stat` in `src/stats_cli/stats.py`. A plain
name may end in digits (`r2`) only if it can't also be read as a request for
a parameterized family; the registry rejects such a clash. A parameterized
family is registered by its base name (`q`) with `param=` set. `Sample`
caches the mean, deviations and standard deviation, so they're computed once
per column.

[How stats-cli is built](https://github.com/donalgrant/stats-cli/blob/main/docs/DESIGN.md)
describes the design for developers: the registry, the shared sample, the
weighting rules, input and output, the tests, and every change from the
original `pstats.py`, with the reasons.

## License

MIT
