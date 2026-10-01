# The stats user guide

`stats` prints statistics of columns of numbers. It reads numbers from
standard input or from files and prints the statistics you name, one output
row per input column. It is meant for the shell, between commands that make
numbers and commands that use them. This guide starts with a first session
and works up to fits, weights, groups, histograms and confidence intervals.
It ends with recipes and a reference.

Every example in this guide is run by the test suite, and its output is
checked against what's shown here.

Contents:

1. [A first session](#1-a-first-session)
2. [Getting data in](#2-getting-data-in)
3. [Choosing statistics](#3-choosing-statistics)
4. [The statistics](#4-the-statistics)
5. [Output](#5-output)
6. [Comparing columns: correlation and fits](#6-comparing-columns-correlation-and-fits)
7. [Weights and measurement errors](#7-weights-and-measurement-errors)
8. [Groups](#8-groups)
9. [Histograms and sparklines](#9-histograms-and-sparklines)
10. [Confidence intervals](#10-confidence-intervals)
11. [Recipes](#11-recipes)
12. [Errors, warnings and exit status](#12-errors-warnings-and-exit-status)
13. [findgen](#13-findgen)
14. [Option reference](#14-option-reference)

Install with `pipx install stats-cli` (or `uv tool install stats-cli`). That
gives you two commands, `stats` and `findgen`.

---

## 1. A first session

Give `stats` some numbers and it prints a default summary: the count,
mean, standard deviation, minimum, median and maximum.

```console
$ seq 1 10 | stats
         n       mean      stdev        min     median        max
        10        5.5      3.028          1        5.5         10
```

Name the statistics you want, in the order you want them:

```console
$ seq 1 100 | stats n mean stdev q10 q90
         n       mean      stdev        q10        q90
       100       50.5      29.01       10.9       90.1
```

`q10` and `q90` are the 10th and 90th percentiles. A name ending in a
number is a *parameterized* statistic. Section 3 explains them.

Each input column gets its own output row. Here are two columns side by
side, made with `paste`:

```console
$ paste <(seq 1 10) <(seq 10 10 100) | stats mean median max
      mean     median        max
       5.5        5.5         10
        55         55        100
```

`-nh` leaves out the header line, which is handy when another program
reads the output:

```console
$ seq 1 10 | stats -nh mean
       5.5
```

---

## 2. Getting data in

### Whitespace columns

By default fields are separated by any run of spaces or tabs. Blank lines,
and anything after a `#`, are ignored:

<!-- file: temps.txt -->
```text
# hourly temperatures, two sensors
20.1  19.8
20.4  20.0

21.0  20.6   # warming up
21.7  21.1
```

```console
$ stats -f temps.txt mean min max
      mean        min        max
      20.8       20.1       21.7
     20.38       19.8       21.1
```

`-f FILE` reads a file. Without `-f`, `stats` reads standard input, so
`stats mean < temps.txt` gives the same result. Repeat `-f` to combine
several files: their rows are stacked, as if the files were joined with
`cat`. `-` stands for standard input.

### Header rows

If the first line has no numbers at all, it is taken as the column names,
and each output row is labeled with its column's name:

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
```

`--csv` is short for `-d ,`, a comma delimiter. `--tsv` is the same for
tabs, and `-d` takes any single character. Use `--header` to force the
first line to be names, or `--no-header-row` to force it to be data.

A first line that mixes numbers and words is an error, because `stats`
can't tell whether it is names or data.

### Missing values

The `weight` and `age` columns above each have an empty field, so their `n`
is 3. Missing values are skipped by every statistic. These count as
missing:

- empty fields in delimited input;
- the words `nan`, `NA`, `N/A`, `null`, `none` and `-`, in any case;
- fields missing from the end of a short row, with a warning.

Use `--strict` to make any missing value an error instead. Any other word
in a data column is an error, reported with its line number (section 12).

### Choosing columns

`-c` picks columns by number (from 1), by range, or by header name, in the
order you give them:

```console
$ stats --csv -f people.csv -c age,height mean
column       mean
age            41
height      173.2

$ stats --csv -f people.csv -c 2- mean
column       mean
weight         72
age            41
```

`2-` means column 2 to the last, and `2-3` would be columns 2 and 3. Columns
you don't select may contain text. That lets you summarize the numeric
columns of a file that also has names or dates:

<!-- file: runs.txt -->
```text
date        runner  km    minutes
2026-09-01  ana     5.0   27.5
2026-09-02  ben     8.2   44.1
2026-09-04  ana     5.1   26.9
2026-09-06  ben    10.0   55.0
```

```console
$ stats -f runs.txt -c km,minutes n mean max
column           n       mean        max
km               4      7.075         10
minutes          4      38.38         55
```

---

## 3. Choosing statistics

With no statistics named, `stats` prints `n mean stdev min median max`.
`--describe` prints a broader summary, followed by any statistics you add:

```console
$ seq 1 20 | stats --describe
         n       nnan       mean      stdev     stderr        min        plq     median        puq        max       skew       kurt
        20          0       10.5      5.916      1.323          1       5.75       10.5      15.25         20          0       -1.2
```

(`nnan` counts missing values, `plq` and `puq` are the quartiles, and
`skew` and `kurt` describe the shape.)

`stats --list-stats` (or `-l`) lists every statistic with a one-line
description. The `w` and `e` columns show which ones accept weights and
measurement errors (section 7):

```console
$ stats -l | head -6
per-column statistics (w: allowed with -w weights, e: allowed with -e errors):
  n              w e  number of values (total weight with -w)
  nrows          w e  number of rows with a value
  nnan           w e  number of missing (NaN) values
  min            w e  minimum
  max            w e  maximum
```

**Parameterized statistics** have a number in place of the `N` in their
listed name. For example, `qN` is a percentile, so `q25` is the 25th
percentile and `q2.5` the 2.5th. `momN` is a raw moment, so `mom3` is the
mean of x³. The number may be a fraction.

```console
$ seq 1 100 | stats q2.5 q25 q97.5 mom2 trimmean10
      q2.5        q25      q97.5       mom2 trimmean10
     3.475      25.75      97.52       3384       50.5
```

A misspelled or out-of-range name is an error, with a hint about what was
meant:

```console
$ seq 10 | stats q120 2>&1
stats: error: 'q120': percentile 0-100 out of range (see --list-stats)

$ seq 10 | stats qN 2>&1
stats: error: statistic 'qN' needs a number in place of N (e.g. q25) (see --list-stats)
```

---

## 4. The statistics

All statistics skip missing values. A statistic that is undefined for the
data prints `nan`: for example `stdev` of one value, or `kurt` of fewer than
four.

**Counts and location**

| Name | Definition |
|---|---|
| `n` | number of values (the total weight Σw with `-w`) |
| `nrows` | number of rows with a value, even when weighted |
| `nnan` | number of missing values |
| `min`, `max` | minimum, maximum |
| `absmin` | smallest absolute value, min \|x\| |
| `range` | max − min |
| `sum` | Σx |
| `mean` | x̄ = Σx / n |
| `median` | the 50th percentile |
| `mode` | the most frequent value (the smallest, if tied) |
| `gmean` | geometric mean, exp(mean(ln x)); `nan` unless every value is > 0 |
| `hmean` | harmonic mean, n / Σ(1/x); `nan` unless every value is > 0 |
| `trimmeanN` | the mean after dropping N% of the values from *each* end, 0 ≤ N < 50 |

**Spread**

| Name | Definition |
|---|---|
| `stdev` | sample standard deviation, s = √(Σ(x − x̄)² / (n − 1)) |
| `svar` | sample variance, s² |
| `pstdev`, `pvar` | population standard deviation and variance (dividing by n) |
| `stderr` | standard error of the mean, s / √n (1/√Σ(1/σ²) with `-e`) |
| `cv` | coefficient of variation, s / x̄ |
| `absdev` | mean absolute deviation from the mean, Σ\|x − x̄\| / n |
| `mad` | median absolute deviation from the median, median(\|x − median\|) |
| `smad` | 1.4826 × `mad`: a robust estimate of σ for normally distributed data |
| `iqr` | interquartile range, `puq` − `plq` |
| `rms` | root mean square, √(Σx² / n) |

**Percentiles and shape**

| Name | Definition |
|---|---|
| `plq`, `puq` | lower and upper quartiles (25th and 75th percentiles) |
| `qN` | the N-th percentile, 0 ≤ N ≤ 100 |
| `skew` | bias-corrected skewness G1 (as in pandas and Excel) |
| `kurt` | bias-corrected *excess* kurtosis G2 (0 for a normal distribution) |
| `momN` | raw moment, Σx^N / n |
| `devN` | central moment, Σ(x − x̄)^N / n |
| `ndevN` | standardized moment, Σ((x − x̄)/s)^N / n |
| `absmN` | absolute central moment, Σ\|x − x̄\|^N / n |

**With measurement errors** (`-e` only; section 7)

| Name | Definition |
|---|---|
| `chi2` | Σ((x − x̄)/σ)², about the weighted mean |
| `rchi2` | `chi2` / (n − 1) |

**Pictures**

| Name | Definition |
|---|---|
| `spark`, `sparkN` | a sparkline: a 10-bin (or N-bin) histogram drawn as `▁▂▃▄▅▆▇█`; empty bins are blank |

Percentiles interpolate linearly between the sorted values, as numpy and
pandas do by default. That's why the median of 1 to 10 is 5.5.

A robust statistic is one that a few wild values can't move much. Compare
the mean and standard deviation with the median and `smad` when one value
is a typo:

```console
$ printf '%s\n' 10.1 9.8 10.3 9.9 10.0 101 | stats mean stdev median smad
      mean      stdev     median       smad
     25.18      37.14      10.05     0.2965
```

---

## 5. Output

### Tables

The default output is an aligned table. Each value is printed with four
significant digits, in a field at least 10 characters wide. Rows are
labeled when the input has a header row or `-c` is used. `-L` forces
labels on, and `--no-labels` turns them off.

`-p` sets the number of significant digits, and `--fmt` takes a printf
format:

```console
$ seq 1 7 | stats -p 8 mean stdev
      mean      stdev
         4  2.1602469

$ seq 1 7 | stats --fmt %.2f mean stdev
      mean      stdev
      4.00       2.16
```

### One row per statistic

`-T` turns the table around, giving one row per statistic and one column
per input column. This is easier to read when there are many statistics:

```console
$ stats --csv -f people.csv -T n mean median
stat       height     weight        age
n               4          3          3
mean        173.2         72         41
median        173         71         41
```

### CSV, TSV and JSON

`-F csv` and `-F tsv` print delimited output at full precision, for
spreadsheets and other programs. `-F json` prints a list of records, with
undefined values as `null`:

```console
$ stats --csv -f people.csv -c height,age -F csv mean stdev
column,mean,stdev
height,173.25,7.365459931328117
age,41,11

$ stats --csv -f people.csv -c age -F json n mean
[
  {
    "column": "age",
    "n": 3,
    "mean": 41
  }
]
```

`-T` works with every format. In JSON it gives one record per statistic.

---

## 6. Comparing columns: correlation and fits

`-x COL` names a **reference column**. Every other column y is then
compared with it: correlated, and fitted with a straight line
y = a + b·x by least squares. The reference column itself isn't reported.

<!-- file: obs.txt -->
```text
t flux err temp
1 10.2 0.5 20.1
2 12.1 0.4 20.9
3 13.8 0.6 22.2
4 16.3 0.5 22.8
5 17.9 0.7 24.1
```

```console
$ stats -f obs.txt -x t -c flux,temp corr slope slope_err intercept r2
column       corr      slope  slope_err  intercept         r2
flux        0.998       1.96    0.07211       8.18      0.996
temp       0.9946       0.99    0.05972      19.05     0.9892
```

So flux rises by about 1.96 per unit of `t`, give or take 0.07.

| Name | Definition |
|---|---|
| `corr` | Pearson correlation coefficient |
| `rcorr` | Spearman rank correlation (unweighted only) |
| `cov` | sample covariance, dividing by n − 1 |
| `slope`, `intercept` | b and a of the least-squares fit y = a + b·x |
| `slope_err`, `intercept_err` | their standard errors, from the scatter of the residuals (as scipy's `linregress` gives them), or from the known errors with `-e` |
| `r2` | coefficient of determination R² of the fit |
| `rmsres` | RMS of the residuals |
| `chi2fit`, `rchi2fit` | Σ((y − a − b·x)/σ)², and that divided by n − 2 (`-e` only) |

Rows missing either value are skipped for that pair only. These statistics
can be mixed with ordinary ones in the same command.

`--matrix` prints a whole matrix of `corr`, `cov` or `rcorr` between all the
data columns:

```console
$ stats -f obs.txt --matrix corr -c flux,temp,err
column       flux       temp        err
flux            1     0.9869     0.6623
temp       0.9869          1     0.7607
err        0.6623     0.7607          1
```

---

## 7. Weights and measurement errors

### Frequency weights: `-w`

`-w COL` says how many times each row counts. **Every statistic is computed
as if each row were repeated that many times**, so these two give the same
answers:

<!-- file: counts.txt -->
```text
score count
1 3
2 1
5 2
```

<!-- file: repeated.txt -->
```text
1
1
1
2
5
5
```

```console
$ stats -f counts.txt -w count -c score n mean stdev median q90
column          n       mean      stdev     median        q90
score           6        2.5      1.975        1.5          5

$ stats -f repeated.txt n mean stdev median q90
         n       mean      stdev     median        q90
         6        2.5      1.975        1.5          5
```

Weights needn't be whole numbers. Rows with zero weight are ignored, and
negative weights are an error. `trimmeanN` and `rcorr` don't accept
weights.

### Measurement errors: `-e`

`-e COL` gives each value an uncertainty σ (the same σ column applies to
every data column). The values are then weighted by 1/σ², so precise
measurements count more:

- `mean` is the inverse-variance weighted mean;
- `stderr` is its uncertainty, 1/√Σ(1/σ²);
- `chi2` and `rchi2` measure how well the values agree within their
  errors (`rchi2` near 1 means the scatter matches the errors);
- with `-x`, the fit becomes weighted least squares.

```console
$ stats -f obs.txt -x t -e err -c flux slope slope_err intercept rchi2fit
column      slope  slope_err  intercept   rchi2fit
flux        1.974     0.1756      8.166     0.1701
```

A small `rchi2fit` like this one means the points scatter less than their
error bars suggest, so the errors may be overestimated.

A weighted median or standard deviation has no standard meaning when the
weights are errors. So `stats` refuses those statistics with `-e`, rather
than quietly computing something else:

```console
$ stats -f obs.txt -e err -c flux median 2>&1
stats: error: median is not defined with -e (measurement errors); use -w for frequency weights
```

Statistics that don't depend on weights, such as `n`, `min` and `max`, work
with `-e` too. `stats -l` marks what each statistic accepts.

---

## 8. Groups

`-g COL` splits the rows by the value in `COL` and computes every
statistic for each group. The keys may be words or numbers. Groups are
listed in sorted order, numerically when every key is a number:

<!-- file: bands.txt -->
```text
band flux err
V 15.2 0.4
B 13.1 0.5
R 17.0 0.6
V 14.8 0.3
B 12.7 0.4
R 16.4 0.5
V 15.5 0.5
B 13.4 0.6
R 16.9 0.4
```

```console
$ stats -f bands.txt -g band -c flux n mean stderr
band column          n       mean     stderr
B    flux            3      13.07     0.2028
R    flux            3      16.77     0.1856
V    flux            3      15.17     0.2028

$ stats -f bands.txt -g band -c flux -e err mean stderr rchi2
band column       mean     stderr      rchi2
B    flux        12.97     0.2771     0.5184
R    flux        16.77     0.2771     0.4001
V    flux        15.05     0.2164     0.8225
```

Rows with no key are skipped, with a warning. Groups work with `-x`, `-w`,
`-e`, histograms, confidence intervals and every output format. In CSV and
JSON the group is a field of its own:

```console
$ stats -f bands.txt -g band -c flux -F csv n mean
band,column,n,mean
B,flux,3,13.066666666666665
R,flux,3,16.766666666666666
V,flux,3,15.166666666666666
```

The runs from section 2 can be grouped by runner the same way:

```console
$ stats -f runs.txt -g runner -c km,minutes sum
runner column         sum
ana    km            10.1
ana    minutes       54.4
ben    km            18.2
ben    minutes       99.1
```

---

## 9. Histograms and sparklines

`--hist` prints a histogram of each column instead of statistics:

```console
$ seq 1 50 | awk '{print $1*$1 % 37}' | stats --hist --bins 6
        lo         hi      count
         0          6          9  ████████████████████████████████▊
         6         12         11  ████████████████████████████████████████
        12         18          6  █████████████████████▉
        18         24          3  ██████████▉
        24         30         11  ████████████████████████████████████████
        30         36         10  ████████████████████████████████████▍
```

- `--bins` takes a number, or one of numpy's rules: `auto` (the default),
  `fd`, `doane`, `scott`, `stone`, `rice`, `sturges` or `sqrt`.
- `--range LO:HI` fixes the range, for comparing histograms of different
  data.
- With `-g`, every group's histogram uses the same bins.
- With `-w`, the counts are sums of weights.
- `-F csv`, `tsv` and `json` print the `lo`, `hi` and `count` of each bin,
  without bars.

For a quick look, the `spark` statistic draws a small histogram on one
line, so it fits in a table with other statistics. `--ascii` draws with
plain characters, for terminals or files that don't handle Unicode well:

```console
$ seq 1 50 | awk '{print $1*$1 % 37}' | stats n mean spark
         n       mean      spark
        50      17.86 ▆▆▆▅▃▃▃█▂█

$ seq 1 50 | awk '{print $1*$1 % 37}' | stats --ascii n mean spark20
         n       mean              spark20
        50      17.86 *-== @# =  = ==#- #=
```

---

## 10. Confidence intervals

`--ci LEVEL` adds a `STAT_lo` and `STAT_hi` column after each statistic: a
LEVEL% confidence interval, found by the bootstrap. The rows are resampled
with replacement many times (`--bootstrap`, 1,000 by default), the
statistic is recomputed on each resample, and the interval is the central
LEVEL% of the results. This works for any numeric statistic, including
medians, percentiles and fit slopes, for which there's often no simple
formula.

```console
$ seq 1 50 | awk '{print $1*$1 % 37}' | stats --ci 95 --seed 1 mean median
      mean    mean_lo    mean_hi     median  median_lo  median_hi
     17.86      14.62      20.96         16         11       25.5
```

The resampling is random, so the intervals change slightly from run to
run. `--seed` makes them repeatable. With `-g`, each group's intervals
depend only on the seed and that group's data, so adding another group to
the input doesn't change them.

Each row keeps its weight and reference value when it's resampled, so
weighted statistics and fits are resampled correctly. The cost grows with
the number of rows times the number of resamples. 1,000 resamples of
100,000 rows take a second or two, and `stats` warns when a run is likely
to be slow.

---

## 11. Recipes

**Add an index column and fit a trend.** `findgen` (section 13) numbers the
lines, and `paste` puts the numbers beside the data:

<!-- file: daily.txt -->
```text
101.2
102.0
101.7
103.1
103.9
104.2
```

```console
$ findgen 6 | paste - daily.txt | stats -x 1 slope slope_err r2
column      slope  slope_err         r2
2          0.6314    0.09343     0.9195
```

So the series rises by about 0.6 per day.

**Statistics of a derived quantity.** Compute it with `awk` first. Here is
the pace of each run, in minutes per km:

```console
$ awk 'NR > 1 {print $4 / $3}' runs.txt | stats -p 3 n mean min max
         n       mean        min        max
         4       5.41       5.27        5.5
```

**One number for a script.** CSV output without a header or labels gives a
bare number, at full precision, ready for a shell variable. (`-c` turns row
labels on, so they have to be turned off again.)

```console
$ mean=$(stats -F csv -nh --no-labels -f temps.txt -c 1 mean); echo "sensor 1 averaged $mean"
sensor 1 averaged 20.8
```

Add `--fmt %.1f` (or `-p`) for a fixed number of decimals.

**Compare files.** Use `-F csv -nh --no-labels` to write one line of
results per file, ready to collect into a table:

```console
$ for f in temps.txt daily.txt; do printf '%s,' "$f"; stats -nh --no-labels -F csv -f "$f" -c 1 n mean; done
temps.txt,4,20.8
daily.txt,6,102.68333333333334
```

**Check data before using it.** `--strict` fails on any missing value, and
the exit status says whether the data passed:

```console
$ stats --strict --csv -f people.csv n > /dev/null 2>&1 || echo "people.csv has gaps"
people.csv has gaps
```

---

## 12. Errors, warnings and exit status

Errors and warnings go to standard error, so they never mix with the
results on standard output. The exit status tells a script what happened:

| Status | Meaning |
|---|---|
| 0 | success |
| 1 | a problem with the data: a file that can't be read, a value that isn't a number, no data |
| 2 | a problem with the command: an unknown statistic or option, or options that can't be combined |

```console
$ printf '1\n2\nx\n' | stats mean 2>&1; echo "status $?"
stats: error: line 3: non-numeric value 'x'
status 1

$ seq 5 | stats medain 2>&1; echo "status $?"
stats: error: unknown statistic 'medain' (see --list-stats)
status 2

$ seq 5 | stats slope 2>&1; echo "status $?"
stats: error: slope needs a reference column (-x COL)
status 2
```

Command errors are found before any input is read. A misspelled statistic
fails at once, without waiting for a long pipeline.

Warnings, such as a short row padded with missing values, don't stop the
run. `-q` silences them, and `-v` reports details such as the number of
rows read:

```console
$ printf '1 2\n3\n5 6\n' | stats -v mean 2>&1
stats: warning: 1 row(s) have fewer than 2 fields; missing values ignored
stats: read 3 rows x 2 columns
stats: 2: skipped 1 row(s) with missing values
      mean
         3
         4
```

---

## 13. findgen

`findgen N` prints N numbers, one per line, starting at 0. It is named
after IDL's `FINDGEN`.

```console
$ findgen 4
0
1
2
3

$ findgen -o 1 -s 10 3
1
11
21

$ findgen -r 3
2
1
0
```

| Option | Meaning |
|---|---|
| `-o`, `--offset` | the first number (default 0) |
| `-s`, `--step` | the increment (default 1; may be negative, not 0) |
| `-r`, `--reverse` | count down instead of up |

`findgen` is like `seq`, but it takes a **count** instead of endpoints, so
`findgen N` is `seq 0 $((N-1))` without the off-by-one arithmetic. It also
behaves the same everywhere when the count is zero: `findgen 0` prints
nothing. In contrast, `seq 0 -1` prints nothing with GNU `seq` (Linux) but
counts down with BSD `seq` (macOS). For fractional steps or custom
formats, use `seq`.

---

## 14. Option reference

```text
stats [options] [STAT ...]
```

Options and statistic names may be given in any order.

**General**

| Option | Meaning |
|---|---|
| `-l`, `--list-stats` | list the statistics and exit |
| `--describe` | a broad summary: `n nnan mean stdev stderr min plq median puq max skew kurt`, plus any statistics named |
| `-v`, `--verbose` | report details on stderr |
| `-q`, `--quiet` | suppress warnings |
| `-V`, `--version` | print the version |
| `-h`, `--help` | print help |

**Input**

| Option | Meaning |
|---|---|
| `-f FILE`, `--file FILE` | read FILE (repeat to stack several; `-` is stdin) |
| `-d CHAR`, `--delimiter CHAR` | field delimiter (default: any whitespace) |
| `--csv`, `--tsv` | comma- or tab-delimited input |
| `--header`, `--no-header-row` | the first line is, or is never, column names (default: names if it has no numbers) |
| `-c SPEC`, `--columns SPEC` | columns to use: `2`, `2,5`, `2-4`, `3-`, `height,weight` |
| `--strict` | make missing values an error |

**Relations, weights and groups**

| Option | Meaning |
|---|---|
| `-x COL`, `--ref COL` | reference column for `corr`, `cov` and fits |
| `-w COL`, `--weights COL` | frequency weights |
| `-e COL`, `--errors COL` | measurement errors σ (weights 1/σ²) |
| `-g COL`, `--group COL` | statistics for each value in COL |
| `--matrix corr\|cov\|rcorr` | the matrix of that statistic between all data columns |

`-x`, `-w`, `-e` and `-g` each take one column, chosen as with `-c`, and
that column is not reported as data.

**Histograms and intervals**

| Option | Meaning |
|---|---|
| `--hist` | print histograms instead of statistics |
| `--bins N\|RULE` | number of bins or a numpy rule (default `auto`) |
| `--range LO:HI` | histogram range |
| `--ascii` | ASCII bars and sparklines |
| `--ci LEVEL` | add a LEVEL% bootstrap interval for each statistic |
| `--bootstrap N` | number of resamples (default 1000) |
| `--seed S` | random seed, for repeatable intervals |

**Output**

| Option | Meaning |
|---|---|
| `-nh`, `--no-header` | omit the header line |
| `-F FMT`, `--format FMT` | `table` (default), `csv`, `tsv` or `json` |
| `-T`, `--transpose` | one row per statistic |
| `-L`, `--labels` / `--no-labels` | force row labels on or off |
| `-p N`, `--precision N` | significant digits (default 4 in tables, full in CSV/TSV) |
| `--fmt PRINTF` | printf-style number format, such as `%.3f` |
