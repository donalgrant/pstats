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

$ cat people.csv
height,weight,age
170,65,30
182,80,
165,,41
176,71,52
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
stats [options] STAT [STAT ...]
```

Statistic names and options can be given in any order.

**General options**

| Option | Meaning |
|---|---|
| `-l`, `--list-stats` | list the available statistics and exit |
| `-v`, `--verbose` | report parsing details on stderr |
| `-q`, `--quiet` | suppress warnings |
| `-V`, `--version` | print the version |

**Input options**

| Option | Meaning |
|---|---|
| `-f FILE`, `--file FILE` | read `FILE` instead of stdin. Repeat it to concatenate the rows of several files; `-` means stdin. |
| `-d CHAR`, `--delimiter CHAR` | field delimiter (the default is any whitespace) |
| `--csv`, `--tsv` | shorthand for `-d ,` and a tab delimiter |
| `--header` | always treat the first line as column names |
| `--no-header-row` | never treat the first line as column names |
| `-c SPEC`, `--columns SPEC` | columns to use, in the order given. Columns are numbered from 1 and can also be chosen by header name: `2`, `2,5`, `2-4`, `3-` (column 3 to the last), `height,weight` |
| `--strict` | treat missing or NaN values as an error instead of skipping them |

**Output options**

| Option | Meaning |
|---|---|
| `-nh`, `--no-header` | omit the header line |
| `-F FMT`, `--format FMT` | `table` (the default), `csv`, `tsv` or `json` |
| `-T`, `--transpose` | one row per statistic instead of one per column |
| `-L`, `--labels` / `--no-labels` | force the row-label column on or off |
| `-p N`, `--precision N` | significant digits (the default is 4 in tables and full precision in csv/tsv) |
| `--fmt PRINTF` | printf-style number format, such as `%.3f` |

**Input.**
- Blank lines and anything after `#` are ignored.
- A first line with **no** numeric fields is taken as the column names. Use
  `--header` or `--no-header-row` to override this.
- Tokens like `nan` or `NA` count as missing values. So do empty delimited
  fields and fields missing from short rows.
- Missing values are left out of every statistic, and `n` counts only the
  values present. Use `--strict` to make missing values an error instead.
- Any other non-numeric token is an error.

**Output.**
- A header line comes first, unless `-nh` is given. Then there is one line
  per input column.
- By default each value is printed with format `%10.4g`, and statistics
  appear in the order you requested them.
- Rows get a leading label (the column name or number) when the input had a
  header row or `-c` was used. Otherwise the output is unlabeled, as in the
  original tool.
- `csv` and `tsv` output uses full precision.
- `json` output is a list of objects such as
  `{"column": "height", "mean": 173.25}`. Undefined values become `null`.

**Exit status.**
- `0` on success.
- `1` for input data problems, such as an unreadable file or a non-numeric
  value.
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
