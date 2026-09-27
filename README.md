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

**Weights and relations between columns** (see [below](#relations-between-columns))

| Option | Meaning |
|---|---|
| `-x COL`, `--ref COL` | reference column for `corr`, `cov` and the fit statistics. The reference column's own row is not printed. |
| `-w COL`, `--weights COL` | frequency weights: each row counts w times |
| `-e COL`, `--errors COL` | measurement errors σ, used as inverse-variance weights 1/σ². The same σ column applies to every data column. |
| `--matrix corr\|cov\|rcorr` | print the matrix of that statistic between all data columns |

`-x`, `-w` and `-e` columns are chosen the same way as with `-c`, and are
never treated as data columns themselves.

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

**Counts and location**

| Name | Definition |
|---|---|
| `n` | number of non-missing values (the total weight Σw with `-w`) |
| `nrows` | number of rows with a value, even when weighted |
| `nnan` | number of missing values |
| `min`, `max` | minimum, maximum |
| `absmin` | min(\|x\|) |
| `range` | max − min |
| `sum` | Σx |
| `mean` | x̄ = Σx / n |
| `median` | 50th percentile |
| `mode` | most frequent value (the smallest, if tied) |
| `gmean` | geometric mean, exp(mean(ln x)). `nan` unless all values are > 0. |
| `hmean` | harmonic mean, n / Σ(1/x). `nan` unless all values are > 0. |
| `trimmeanN` | mean after dropping N% of the values from *each* end, 0 ≤ N < 50 (as in scipy's `trim_mean`) |

**Spread and shape**

| Name | Definition |
|---|---|
| `stdev` | sample standard deviation s = √(Σ(x−x̄)² / (n−1)) |
| `svar` | sample variance s² |
| `pstdev`, `pvar` | population standard deviation and variance (dividing by n) |
| `stderr` | **standard error of the mean** (the standard deviation of the mean of n measurements), s / √n. With `-e` it is 1/√Σ(1/σ²). |
| `cv` | coefficient of variation, s / x̄ |
| `mad` | median absolute deviation from the median, median(\|x − median\|) |
| `smad` | 1.4826 × `mad`: a robust estimate of σ for normally distributed data |
| `iqr` | interquartile range, `puq` − `plq` |
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
| `chi2`, `rchi2` | Σ((x−x̄)/σ)² about the weighted mean, and chi2 / (n−1). These require `-e`. |

Percentiles interpolate linearly between order statistics, which is the
numpy and pandas default. Statistics that are undefined for the data print
`nan`, for example `stdev` of a single value or `kurt` with fewer than 4
values.

## Relations between columns

Use `-x COL` to name a reference column. Each other column y is then compared
with it: correlated, and fitted by least squares with a straight line
y = a + b·x. The output keeps one row per column, and these statistics can be
mixed with ordinary ones.

```console
$ cat obs.txt
t flux err temp
1 10.2 0.5 20.1
2 12.1 0.4 20.9
3 13.8 0.6 22.2
4 16.3 0.5 22.8
5 17.9 0.7 24.1
$ stats -f obs.txt -x t -c flux,temp corr slope slope_err r2
column       corr      slope  slope_err         r2
flux        0.998       1.96    0.07211      0.996
temp       0.9946       0.99    0.05972     0.9892

$ stats -f obs.txt -x t -e err -c flux slope slope_err intercept rchi2fit
column      slope  slope_err  intercept   rchi2fit
flux        1.974     0.1756      8.166     0.1701

$ stats -f obs.txt --matrix corr -c flux,temp,err
column       flux       temp        err
flux            1     0.9869     0.6623
temp       0.9869          1     0.7607
err        0.6623     0.7607          1
```

| Name | Definition |
|---|---|
| `corr` | Pearson correlation coefficient |
| `rcorr` | Spearman rank correlation (unweighted only) |
| `cov` | sample covariance, dividing by n−1 |
| `slope`, `intercept` | b and a of the least-squares fit y = a + b·x |
| `slope_err`, `intercept_err` | their standard errors. Without `-e` these are scaled by the residual scatter, as in scipy's `linregress`. With `-e` they come from the known σ alone. |
| `r2` | coefficient of determination R² of the fit |
| `rmsres` | RMS of the residuals |
| `chi2fit`, `rchi2fit` | Σ((y − a − b·x)/σ)², and that value / (n−2). These require `-e`. |

Rows where either the column or the reference is missing are skipped for that
pair only.

## Weights

- **`-w COL` (frequency weights).** Every statistic is computed as if each row
  appeared w times. For integer weights the results equal those for the
  expanded data, and `n` is Σw. Rows with zero weight are ignored, and
  negative weights are an error. `trimmeanN` and `rcorr` don't accept
  weights.
- **`-e COL` (measurement errors σ).** Rows are weighted by 1/σ².
  - `mean` is the inverse-variance weighted mean and `stderr` is 1/√Σ(1/σ²).
  - `chi2` and `rchi2` measure scatter about that mean.
  - The fit statistics become proper weighted least squares.
  - Statistics with no standard inverse-variance definition, such as
    `median` and `stdev`, are refused rather than silently computed
    unweighted.
  - Weight-independent statistics (`n`, `min`, `max`, `range` and so on)
    still work.

`stats --list-stats` marks each statistic with the weight modes it accepts.

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
