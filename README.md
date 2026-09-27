# stats

Column statistics for whitespace-delimited numeric data, from the command line.

`stats` reads numbers from standard input and prints the statistics you name,
one output row per input column. It is a Python/numpy port of an older C++
tool, designed to sit in Unix pipelines.

```console
$ seq 1 100 | stats n mean stdev q10 q90
         n       mean      stdev        q10        q90
       100       50.5      29.01       10.9       90.1

$ paste <(seq 1 10) <(seq 10 10 100) | stats -nh mean median
       5.5        5.5
        55         55
```

The package also installs `findgen`, a small index generator (`findgen 5`
prints 0 through 4).

## Install

Requires Python 3.10+ and numpy. It's best installed as an isolated tool:

```console
$ pipx install git+https://github.com/donalgrant/pstats.git
# or
$ uv tool install git+https://github.com/donalgrant/pstats.git
```

To install from a local checkout for development, use
`python -m venv .venv && .venv/bin/pip install -e '.[dev]'`.

## Usage

```
stats [-nh] [-v | -q] STAT [STAT ...] < data
```

| Option | Meaning |
|---|---|
| `-nh`, `--no-header` | omit the header line |
| `-l`, `--list-stats` | list the available statistics and exit |
| `-v`, `--verbose` | report parsing details on stderr |
| `-q`, `--quiet` | suppress warnings |
| `-V`, `--version` | print the version |

**Input.** Fields are separated by any whitespace.
- Blank lines and anything after `#` are ignored.
- Tokens like `nan` or `NA` count as missing, and so do fields missing from
  short rows. Missing values are left out of every statistic, and `n` counts
  only the values present.
- Any other non-numeric token is an error.

**Output.**
- A right-aligned header line, unless `-nh` is given.
- Then one line per input column. Each value is printed with format
  `%10.4g`, and statistics appear in the order you requested them.

**Exit status.**
- `0` on success.
- `1` for bad input data.
- `2` for a usage error, such as an unknown statistic.

Errors and warnings go to stderr.

## Statistics

For the parameterized statistics (`qN`, `momN`, `devN`, `ndevN`, `absmN`),
replace `N` with a number. For example, `q25` is the 25th percentile, `q2.5`
the 2.5th percentile, and `mom3` the third raw moment. `N` may be fractional.

| Name | Definition |
|---|---|
| `n` | number of non-missing values |
| `min`, `max` | minimum, maximum |
| `absmin` | min(\|x\|) |
| `range` | max − min |
| `sum` | Σx |
| `mean` | x̄ = Σx / n |
| `median` | 50th percentile |
| `stdev` | sample standard deviation s = √(Σ(x−x̄)² / (n−1)) |
| `svar` | sample variance s² |
| `stderr` | standard error of the mean, s / √n |
| `skew` | bias-corrected skewness G1 (as in pandas and Excel) |
| `kurt` | bias-corrected **excess** kurtosis G2 (0 for a normal distribution) |
| `rms` | √(Σx² / n) |
| `absdev` | mean absolute deviation, Σ\|x−x̄\| / n |
| `plq`, `puq` | lower and upper quartiles (25th and 75th percentiles) |
| `qN` | N-th percentile, 0 ≤ N ≤ 100 |
| `momN` | raw moment, Σx^N / n |
| `devN` | central moment, Σ(x−x̄)^N / n |
| `ndevN` | standardized moment, Σ((x−x̄)/s)^N / n (with the sample s) |
| `absmN` | absolute central moment, Σ\|x−x̄\|^N / n |

Percentiles interpolate linearly between order statistics, which is the
numpy and pandas default. Statistics that are undefined for the data print
`nan`, for example `stdev` of a single value or `kurt` with fewer than 4
values.

## findgen

```
findgen N [-o OFFSET] [-s STEP] [-r]
```

Prints `OFFSET, OFFSET+STEP, …` (N values), one per line. `-r` reverses the
order. The name comes from IDL's `FINDGEN`.

## Development

```console
$ .venv/bin/pytest          # tests, including golden-output checks against the original pstats
$ .venv/bin/ruff check . && .venv/bin/ruff format --check .
```

To add a statistic, register a `Stat` in `src/stats_cli/stats.py`. Plain stat
names must not end in a digit. A parameterized family is registered by its
base name (`q`) with `param=` set. `Sample` caches the mean, deviations and
standard deviation, so they're computed once per column.

## License

MIT
