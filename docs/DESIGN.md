# How stats-cli is built

This guide explains the design of stats-cli for developers: what each module
does, how the modules fit together, why they were built this way, and how
the package differs from the script it replaced. It is also meant to teach.
Several ideas here apply well beyond computing statistics:

- describing a family of operations as data in a registry, instead of as
  branches in code;
- computing shared intermediate results once per input, lazily;
- defining weighted statistics by a single rule, which also gives a way to
  test them;
- a fast path that falls back to a careful path;
- validating everything before reading any input.

Where a choice has a reason that isn't obvious, or a first attempt went
wrong, this guide says so.

stats began as a C++ command-line tool. `pstats.py` (2023) was its first
Python version: a 132-line script built on pandas, with a companion script,
`findgen.py`. The package keeps that script's interface and output, but the
code was rewritten. Section 2 compares the designs, and section 10 lists
every change in behavior, with the reason for each. The original script is
in git history (`git show 6d6dab5:pstats.py`).

Contents:

1. [The layers](#1-the-layers)
2. [From pstats.py to stats-cli](#2-from-pstatspy-to-stats-cli)
3. [The registry: statistics as data](#3-the-registry-statistics-as-data)
4. [Sample: compute once, lazily](#4-sample-compute-once-lazily)
5. [The statistics](#5-the-statistics)
6. [Reading input: `io.py`](#6-reading-input-iopy)
7. [Output: `output.py`](#7-output-outputpy)
8. [Groups, histograms and the bootstrap: `analysis.py`](#8-groups-histograms-and-the-bootstrap-analysispy)
9. [The command line: `cli.py`, and `findgen`](#9-the-command-line-clipy-and-findgen)
10. [Changes from pstats.py, and why](#10-changes-from-pstatspy-and-why)
11. [Testing](#11-testing)
12. [Lessons from the bugs](#12-lessons-from-the-bugs)
13. [Exercises](#13-exercises)

---

## 1. The layers

The package is about 1,700 lines of Python in `src/stats_cli/`. Its only
runtime dependency is numpy. Each layer depends only on the layers below
it:

```
  command line   cli.py         options, validation, the compute loop, exit codes
                 findgen.py     (a separate, tiny command)
                     │
  around stats   io.py          text → Table (numbers, labels, special columns, group keys)
                 analysis.py    groups, histogram bins, bootstrap intervals
                 output.py      results → table, csv, tsv or json
                     │
  statistics     stats.py       the built-in statistics, registered in BUILTIN
                     │
  core           registry.py    Sample (one column, prepared), Stat, Request, Registry
```

| module | lines | role |
|---|---:|---|
| `registry.py` | 188 | the vocabulary: what a statistic is, how a name on the command line becomes one, and the data it runs on |
| `stats.py` | 353 | about 50 statistics, each a few lines, plus their conventions |
| `io.py` | 316 | reading whitespace or delimited text, headers, column selection, missing values |
| `analysis.py` | 139 | grouping, histograms, percentile bootstrap |
| `output.py` | 194 | aligned tables, CSV/TSV, JSON, histogram bars |
| `cli.py` | 470 | argparse, checking options, and the loop over groups and columns |
| `findgen.py` | 48 | index sequences |

Two rules hold throughout:

- **The statistics know nothing about input or output.** A statistic is a
  function from a `Sample` to a number (or, for sparklines, a string). It
  doesn't know whether the data came from CSV, whether it's in a group, or
  whether it will be printed as JSON. That's why every statistic works with
  every input format, grouping and output format without extra code.
- **`main(argv)` returns an exit status.** The tests call it in-process with
  a fake stdin and read what it printed (`tests/conftest.py`). The whole
  suite of 310 tests runs in about 2 seconds.

---

## 2. From pstats.py to stats-cli

`pstats.py` had three parts:

- a dictionary from names to lambdas over a pandas Series
  (`'mean': lambda x: x.mean()`);
- a loop that found parameterized names such as `q25` with a regex and added
  a new lambda to that dictionary for each one;
- a double loop over columns and statistics, which **copied and sorted the
  column again for every statistic** before calling the lambda, and printed
  `'{:10.4g}'` with a space after it.

That was a reasonable first design, and the package keeps its central idea:
statistics live in a table keyed by name, not in an if/elif chain. What
changed, and why:

| pstats.py | stats-cli | why |
|---|---|---|
| a dict of lambdas | a `Registry` of `Stat` records: name, description, function, parameter rule, allowed weight modes, flags | `--list-stats` can describe each statistic; options can be checked before reading input; the registry checks that names can't be read two ways |
| `q25` handled by adding a closure to the dict at run time | `Registry.resolve()` returns a `Request`: the `Stat` bound to its argument | the registry isn't changed while it's in use; errors (`q120`, `qN`, `mean2`) are found and explained in one place |
| pandas Series | numpy arrays | about 8× faster on large inputs and 3× faster to start; the moments used `Series.map` with a Python lambda per element |
| copy and sort the column per statistic | a `Sample` per column that caches its mean, deviations, standard deviation and sorted order | the work shared between statistics is done once; nothing needs a full sort (quantiles use numpy's partial sort) |
| `pd.read_csv(delimiter='\s+')` | `io.read_table`: numpy's C parser first, a careful Python parser if that fails | the same speed on clean input; on bad input, an error that names the line |
| print inside the loop | compute a grid of values, then `output.render` | the same results can be a table, CSV, TSV, JSON or transposed |
| errors printed to stdout, then `sys.exit()` (status 0) | stderr, status 1 (data) or 2 (usage) | in a pipeline, stdout is data and the status says whether it is valid |

The **output is unchanged**. The default table still uses 10-character
right-aligned fields with 4 significant digits (`output.MIN_WIDTH`, and
`precision` defaults to 4 for tables), so every statistic `pstats.py` could
compute prints the same text. Two things differ. Lines no longer end with a
trailing space, and a value too wide for its field widens the column instead
of breaking the alignment. The golden tests check this (section 11).

The **definitions are unchanged**, too. `stats.py` begins with the
conventions it inherits from pandas, so that results stay the same:

- `stdev` and `stderr` use n − 1;
- `skew` and `kurt` are the bias-corrected G1 and G2;
- quantiles interpolate linearly.

`_FP_EPS` exists only to match pandas, which treats a central-moment sum
below 1e-14 as exactly zero. Without it, the skewness of constant data
would come out as rounding noise instead of 0.

---

## 3. The registry: statistics as data

`registry.py` has four small classes.

**`Stat`** is a frozen dataclass that describes a statistic:

```python
Stat(
    "q",
    "N-th percentile, e.g. q10, q2.5",
    lambda s, p: _quantile(s, p / 100),
    param="percentile 0-100",
    valid=_percent,
)
```

Its fields:

- `param` makes it a family: on the command line `q` takes a number (`q25`).
- `valid` checks that number.
- `modes` lists the weight modes it is defined for: unweighted, frequency
  weights (`-w`), or measurement errors (`-e`).
- `cross` marks statistics that compare a column with the reference column
  (`-x`).
- `empty_ok` and `text` handle empty columns and string results.

Because these are fields, not code, the command line can check a request
completely before any data is read:

```text
$ seq 10 | stats slope
stats: error: slope needs a reference column (-x COL)
$ printf '1 0.5\n2 0.5\n' | stats -e 2 median
stats: error: median is not defined with -e (measurement errors); use -w for frequency weights
```

**`Request`** is a statistic bound to its argument and its label: the
`q25` in `q25` is the label, `q` the `Stat`, 25 the argument. Calling a
`Request` on a `Sample` does three things:

- it handles the empty column (NaN, or `""` for text);
- it silences numpy's floating-point warnings, because a statistic of
  degenerate data is NaN, not an error;
- it converts the result to a float.

None of the statistics has to repeat that.

**`Registry.resolve`** turns a command-line name into a `Request`:

1. Plain names are tried first.
2. Then the family regex `^([A-Za-z_]+?)(\d+(?:\.\d*)?)$` splits `q2.5` into
   `q` and `2.5`.
3. If neither matches, it explains why: `qN` needs a number, `mean2` names no
   family, and `q120` is out of range.

```text
$ seq 10 | stats qN
stats: error: statistic 'qN' needs a number in place of N (e.g. q25) (see --list-stats)
$ seq 10 | stats q120
stats: error: 'q120': percentile 0-100 out of range (see --list-stats)
```

One subtle point: `r2` (R² of a fit) is a plain name that ends in digits.
If a family `r` ever existed, `r2` could mean either. So `Registry.add`
refuses to register a name that could be read both ways, and the ambiguity
shows up when the package is imported, not as a wrong answer later. **Check
the ambiguity of a naming scheme when names are registered, not when they
are used.**

---

## 4. Sample: compute once, lazily

A `Sample` is one column prepared for the statistics:

- rows with a missing value are dropped, and so are rows with a missing or
  zero weight;
- `nnan` counts the missing values;
- with `-x`, the reference column is kept alongside, for the paired
  statistics.

Many statistics need the same intermediate values, so `Sample` provides
them as `functools.cached_property`:

| property | used by |
|---|---|
| `n` (the total weight, with `-w`) | nearly everything |
| `mean` | `stdev`, `skew`, `kurt`, `devN`, `cv`, ... |
| `dev` = x − mean | every central moment |
| `std` | `stdev`, `stderr`, `ndevN`, `cv` |
| `sorted` (with cumulative weights) | weighted quantiles, `trimmeanN` |
| `pair` (rows present in both columns) | every `-x` statistic |

`stats --describe` asks for 12 statistics. Each intermediate value is
computed the first time one of them needs it, and then reused. A statistic
nobody asked for costs nothing. `pstats.py` did the opposite: it copied and
sorted the column 12 times.

Unweighted quantiles don't use `sorted` at all. They call `np.quantile`,
which uses a partial sort (introselect) and runs in linear time. **Cache
what is shared; don't compute anything until something asks for it.**

---

## 5. The statistics

`stats.py` is a list of `Stat` records with small helper functions, all
registered into `BUILTIN`. Most statistics are one line. A few ideas are
worth explaining.

### Frequency weights mean replication

What should a weighted median be, or a weighted kurtosis? Textbooks give
several definitions. stats-cli uses one rule for every statistic:

> With `-w`, every statistic is what it would be if each row were repeated
> w times.

This rule decides every case:

- `n` is the total weight;
- `stdev` divides by (total weight − 1);
- the weighted quantile finds its position, h = (W − 1)·p, in the
  *virtually* repeated sorted data, using cumulative weights and
  `searchsorted`, without building the repeated data
  (`_quantile`);
- `mode` counts with `np.bincount(..., weights=w)`.

The rule also gives the test: `test_frequency_weights_equal_replication`
computes every weighted statistic and compares it with the unweighted one
on the repeated data:

```text
$ cat w.txt                       $ cat rep.txt
1 3                               1  1  1  2  5  5   (one per line)
2 1
5 2
$ stats -w 2 -c 1 n mean stdev median q90 < w.txt
column          n       mean      stdev     median        q90
1               6        2.5      1.975        1.5          5
$ stats n mean stdev median q90 < rep.txt
         n       mean      stdev     median        q90
         6        2.5      1.975        1.5          5
```

**A definition you can test by construction beats one you have to look
up.**

### Measurement errors are a different kind of weight

`-e COL` gives each value a standard error σ, and the weight is 1/σ². This
isn't replication. A value with half the error isn't four observations. It
is one observation that is four times as precise. So statistics behave
differently:

- the inverse-variance mean is defined;
- its standard error is 1/√Σw, with no sample spread involved;
- χ² and reduced χ² are defined;
- a fit's slope error comes from the known errors (`var_slope = 1/srr`)
  rather than being scaled by the residuals.

But "the median weighted by inverse variance" has no standard meaning. So
each `Stat` lists the modes it supports, statistics outside them are
rejected with an explanation (`cli._mode_error`), and `-e` becomes a mode
of the sample (`Sample.mode`) rather than just a weights array. **When two
features share a representation (an array of weights) but not a meaning,
keep the meaning in the type.**

### Paired statistics

`_pair_moments` computes the weighted sums for a pair (x, y) once: total
weight, means, and the centered sums Sxx, Syy and Sxy. `corr`, `cov` and
`_fit` all use those sums. `_fit` returns a dict that the slope, intercept,
their errors, r², the RMS residual and χ² read from. `rcorr` (Spearman) is
`corr` applied to average ranks (`_ranks`). Rows missing either value are
dropped from each pair separately, so a gap in one column doesn't remove
rows from the other columns' statistics.

### Robust and descriptive extras

- `mad` is the median of |x − median|.
- `smad` scales `mad` by 1.4826, which makes it estimate σ for normal data.
- `trimmeanN` matches `scipy.stats.trim_mean`.
- `mode` breaks ties by taking the smallest value.
- `spark` returns a string. That's why `Stat.text` exists: the output layer
  passes text through, and the bootstrap skips it.

---

## 6. Reading input: `io.py`

`read_table(text, opts)` returns a `Table`:

- the numeric data, as rows × columns;
- column labels, and whether they came from a header;
- the special columns, by role: reference, weights, errors;
- the group keys, as text.

### A fast path and a careful path

Most input is clean: rectangular and all numeric. For that, numpy's C
parser (`np.loadtxt`) is fast. Real input also has empty CSV fields, `NA`,
short rows and stray words, and on those `loadtxt` raises `ValueError`
without saying much. So `_parse_body` tries `loadtxt` first and, if it
raises, falls back to `_parse_slow`. That function goes line by line:

- `nan`, `NA`, `-` and empty fields become NaN;
- short rows are padded, with a warning;
- any other word is an error that names the line:

```text
$ printf '1\n2\nx\n' | stats mean
stats: error: line 3: non-numeric value 'x'
```

Clean input pays nothing for the careful path. **Let the fast, strict
parser handle the common case, and use its failure as the signal to take
the slow, forgiving one.**

### Headers, by a simple rule

With `header="auto"`, a first line is taken as column names **only if none
of its fields is a number**. A first line with some numbers and some words
is ambiguous, and is an error (`test_mixed_first_line_is_an_error_not_a_header`)
rather than a guess. `--header` and `--no-header-row` override the rule.

### Column specs and roles

`parse_columns` resolves `-c` items to 0-based indices, in the order given:

- `3`, a column number (1-based);
- `2-4` and `3-`, ranges;
- `height`, a header name.

`-x`, `-w`, `-e` and `-g` use the same resolver, with one extra condition:
each must name exactly one column. The special columns are taken out of
the data columns, so `stats -x 1` doesn't report column 1's correlation
with itself.

Columns that aren't selected may contain text. In the careful parser, such
fields are replaced with `"0"` before conversion. The group column is read
a second time as text (`_read_keys`), and the code checks that the keys and
the data rows line up.

Several files (`-f a -f b`) are read separately and stacked by `concat`.
Narrower files are padded with NaN, and a warning is given if the files'
headers differ.

---

## 7. Output: `output.py`

The compute loop produces a grid: one row per column (or per group and
column), one value per statistic. `render` turns that grid into text, and
knows nothing about statistics:

- **table** (the default): numbers right-aligned in fields at least 10
  wide, label columns left-aligned. This is the original's layout, made
  wider where needed.
- **csv** and **tsv**: these use Python's `csv` module (for quoting), and
  print full precision by default. `_exact` prints integral values as
  integers and everything else with `repr`, the shortest text that reads
  back as the same float.
- **json**: a list of records. NaN becomes `null`, because JSON has no NaN,
  and integral values become integers.
- **`-T`** transposes any of these, giving one row per statistic.

`OutputOptions` holds the choices, and `_formatter` builds the
number-to-text function once. The precedence is `--fmt` over `-p` over the
format's default.

Histograms (`render_hist`) draw bars with eighth-block characters, so a bar
can be 3⅜ cells long. A non-empty bin always shows at least `▏`. With
`--ascii`, `#` is used for bars and `.:-=+*#@` for sparklines, for
terminals and files where Unicode isn't welcome.

---

## 8. Groups, histograms and the bootstrap: `analysis.py`

**Groups.** `groups(keys)` returns `(key, row indices)` pairs. Keys are
sorted numerically if every key is a number, and as text otherwise, so `2`
comes before `10` but `B` before `R`. Without `-g`, there is a single group,
`None`, whose rows are `slice(None)`, so the compute loop has only one code
path.

**Histograms.** Bin edges come from numpy (`np.histogram_bin_edges`), with
its named rules (`auto`, `fd`, `sturges`, ...). In a grouped histogram, the
edges are computed **once per column, over all the groups**, so the groups
can be compared bin by bin.

**Bootstrap intervals.** `--ci 95` adds `STAT_lo` and `STAT_hi` columns,
using a percentile bootstrap:

```text
$ seq 1 100 | stats --ci 95 --seed 1 mean
      mean    mean_lo    mean_hi
      50.5      44.62      55.92
```

Three details matter:

- **Whole rows are resampled.** Each drawn row keeps its weight and its
  reference value, so a resampled fit is still a fit of matched pairs.
- **Only usable rows are resampled.** A row is usable if it has a value and
  a valid weight, and for `-x` statistics, also a reference value. So each
  resample is as large as the data behind the estimate. Plain and cross
  statistics have different usable rows, so they are resampled separately.
  (The first version drew from all rows. Resamples then included missing
  values, came out smaller, and the intervals were too wide. A review found
  this; see section 12.)
- **Reproducibility.** Each group's random generator is seeded from
  `--seed` and the group's **key** (`cli._seed`), never its position, and
  numpy's `SeedSequence` accepts the list. So the same `--seed` gives the
  same intervals, and adding or removing other groups doesn't change a
  group's interval. (Before 1.1.0 the seed was `[seed, g]`, with g the
  group's position in sorted order, so a new group that sorted first moved
  every other group's interval slightly.) Without `-g` the seed is still
  `[seed, 0]`, so ungrouped intervals are unchanged.

---

## 9. The command line: `cli.py`, and `findgen`

### Intermixed arguments

`pstats.py` used argparse, and the package still does. But it calls
`parse_intermixed_args`, so statistic names and options can be given in any
order (`stats mean -c 2 median`). Plain `parse_args` stops collecting the
positional `STAT` arguments at the first option.

### Check everything, then read

`main` is in four parts:

1. **Which statistics.** It resolves names, applies presets, and checks
   modes and cross statistics against the options.
2. **Option sanity.** It checks `--fmt` by formatting 1.0 with it, then the
   precision, the delimiter, the `--ci` level, the bins and the range.
3. **Read** the input.
4. **Compute and render.**

Every usage error (exit status 2) is found in parts 1 and 2, before any
input is read. That matters with `stdin`: a typo in a statistic name
shouldn't wait for a 10 GB pipe to finish, or consume it. Data errors
(exit status 1) can only appear in part 3.

The presets are lists of names:

- the default set, `n mean stdev min median max`;
- `--describe`, a broader summary.

They are **filtered quietly** by the weight mode: `--describe -e 2` drops
`median`, which isn't defined with errors. A statistic the user names
explicitly isn't filtered; it gets an error. **Defaults should adapt;
explicit requests should be obeyed or refused.**

### The compute loop

For each group, and each column in it, the loop builds one `Sample` and
evaluates every `Request` on it. With `--ci`, it also adds the bootstrap
pair after each numeric value. The results become a list of labels and a
grid of values, which `render` formats. Histograms and `--matrix` are
separate branches, short because they reuse the same parts. `--matrix`
evaluates one `Request` on a `Sample` for every pair of columns.

### The name

The command is `stats`, the C++ tool's name. The distribution is
`stats-cli`. `pstats` couldn't be used as a module name, because it is a
Python standard-library module (the profiler's statistics). The repository
was renamed to match.

### findgen

`findgen` (named after IDL's FINDGEN) prints `offset, offset+step, ...`. It
builds a `range`, reverses it by slicing (`seq[::-1]` is still a `range`, so
it is never turned into a list), and writes in chunks of 65,536 lines, which
is fast for large N. `--step` is new. The user guide explains how it relates
to `seq`.

---

## 10. Changes from pstats.py, and why

Every behavior that differs from the original script is listed here. Each
was checked by running the original from git history. "Kind" is one of:

- **fix**: the script failed, or contradicted its own help;
- **safety**: a silent failure or crash became a clear error;
- **new**: a capability the script didn't have;
- **kept**: deliberately unchanged.

| pstats.py | stats-cli | kind | why |
|---|---|---|---|
| `absdev` and `absmN` crashed (`TypeError ... NoneType.__format__`): `absm` had no `return` | they work | fix | |
| Python 3.12+ printed `SyntaxWarning`s for `'\w'` and `'\s'` (an error under `-W error`) | raw strings | fix | the warnings mixed into stderr, and a future Python will reject them |
| An unknown statistic printed "statistic foo not available" to **stdout**, with exit status 0 | stderr, status 2, with a reason and a pointer to `--list-stats` | safety | a pipeline can't tell that message from data |
| `-v` printed `df.describe()` and debug lines to **stdout** | stderr | safety | verbose output corrupted the results |
| Non-numeric input, empty input and comment lines: pandas tracebacks | an error naming the line; `#` comments and blank lines ignored | safety | |
| No statistics named: printed blank lines | the default set, `n mean stdev min median max` | fix | blank output looks like success |
| Sorted a copy of the column for every statistic | no full sorts; shared intermediate values cached | — | speed (about 8× on 10M values, 3× faster to start without pandas) |
| `--stat_list`: names, 10 per line | `-l`/`--list-stats`: grouped, described, with weight-mode markers; `--stat_list` still accepted | new | |
| `--no-sort` | accepted, does nothing (hidden from help) | kept | no statistic needs sorted input, but old scripts may pass it |
| `-nh`, `-v`/`-q` mutually exclusive, `qN`-style names | unchanged | kept | the interface |
| 10-wide fields, `%.4g`, a trailing space | the same, without the trailing space; long values widen the column | kept | the output is an interface |
| Each line followed by a space | no trailing space | fix | the golden tests ignore it; nothing should depend on it |
| — | files, delimiters, headers, `-c`, `--strict`; `-F`, `-T`, `-p`, `--fmt`, labels | new | everyday input and output needs |
| — | new statistics, `-x` paired statistics and fits, `--matrix`, `-w`, `-e` | new | |
| — | `-g`, `--hist`, `spark`, `--ci`, `--describe` | new | |
| `findgen` | adds `--step` and `--version`; chunked output | new | |

---

## 11. Testing

The tests (`tests/`, about 310 of them) are in layers.

- **Golden tests** (`test_golden.py`). Outputs from the original
  `pstats.py` are stored in `tests/golden/`. They cover 25 statistic
  requests (`golden/STATS`), which include every statistic it could compute
  except the broken `absdev`, on three fixtures, with and without `-nh`. The rewrite must reproduce them line for line, ignoring the
  trailing space. These are the compatibility contract.
- **Independent references** (`test_stats.py`). Every statistic is compared
  with a different implementation: numpy, scipy (`sem`, `trim_mean`,
  `linregress`, ...), pandas (`skew`, `kurt`, `quantile`), or weighted
  `np.polyfit` for the fits. `test_every_stat_has_a_test` fails if a new
  statistic is registered without a reference. This is the test that would
  have caught `absdev`.
- **Properties by construction.** Frequency-weighted statistics must equal
  the statistics of the repeated data, for both per-column and paired
  statistics. Zero-weight rows must be the same as missing rows.
- **Edge cases.**
  - empty columns, columns of all NaN, and constant data;
  - samples too small for a statistic, which must give NaN, not an error;
  - ragged rows, headers after comments, header-only input;
  - empty CSV fields and header names with spaces.
- **The command line** (`test_cli.py`): every option and error message, and
  which stream it goes to, by calling `main` in-process.
- **Units** for `io`, `output` and `analysis`. For example, the bootstrap
  must be reproducible with a seed, must bracket the estimate, must widen
  with a higher level, and must resample pairs for cross statistics.
- **Docs as tests** (`test_docs.py`). Every ```` ```console ```` block in
  the README and `docs/` runs in bash, and its output must match what the
  block shows. A `<!-- file: NAME -->` comment before a block writes that
  block to a file first, which is how the user guide
  ([`docs/guide.md`](guide.md)) supplies its data. So every example in the
  guide is known to work.

CI runs `ruff check`, `ruff format --check` and the tests on Python 3.10
through 3.13. The release workflow builds from a tag that must match the
package version. A manual run publishes to TestPyPI, and publishing a
GitHub release publishes to PyPI, both through trusted publishing.

---

## 12. Lessons from the bugs

- **An untested statistic was broken for years.** `absm` was missing its
  `return`, so `absdev` and `absmN` returned `None` and crashed when
  formatted. Nothing tested them. *Make the test suite enumerate
  the registry (`test_every_stat_has_a_test`), so a new entry without a test
  fails.*
- **A method that doesn't exist on the oldest supported Python.**
  `int.is_integer()` is new in Python 3.12. Histogram counts are ints, so
  formatting them failed on 3.10 and 3.11. The tests had been run locally on
  3.13 only. CI, which runs 3.10 through 3.13, caught it, and the fix
  converts to float first.
  *Test on the oldest version you claim to support.*
- **A resample that didn't match the estimate.** The first bootstrap drew
  from all rows, including rows with missing values, which the statistic
  then dropped. Resamples were smaller than the data, and the intervals too
  wide. A code review found it. *A bootstrap must resample exactly the rows
  the estimate used.*
- **Two code paths that drifted apart.** Without special columns, rows wider
  than the first row added columns. With `-x`, `-w`, `-e` or `-g` (and no
  `-c`), they were silently dropped. A review found it too, and now both
  paths treat wide rows the same
  (`test_wider_rows_add_columns_whatever_the_options`). *When an option
  takes a different path through the code, test that the common behavior is
  the same on both paths.*
- **A seed tied to position.** The bootstrap seeded group g with
  `[seed, g]`, so adding a group that sorted first changed every other
  group's interval with the same `--seed`. It was found while writing this
  guide. Seeds now come from the group's key. *Derive a random stream from
  the identity of what it's for, not from where it falls in a list.*
- **An option accepted and ignored.** `-F json -T` printed untransposed
  JSON. It now gives one record per statistic. *Every combination of output
  options needs a test, or an error.*
- **Escape sequences in ordinary strings.** `'\w'` worked for years with a
  warning, until Python 3.12 made the warning visible. *Write regexes as
  raw strings.*

---

## 13. Exercises

1. **Add a statistic.** Add `sem` as another name for `stderr`, then
   `geostd` (the geometric standard deviation). What does the registry
   require? Which test fails until you add a reference implementation?
2. **Find the clash.** Register a family `r` (say, "the N-th value in
   rank order"). What happens at import time, and why is that better than
   checking when a name is resolved?
3. **Weighted median by hand.** For values 1, 2, 5 with weights 3, 1, 2,
   trace `_quantile` for p = 0.5: compute h, `lo`, `i` and `j`. Then check
   the result against the repeated data.
4. **Why not -e?** Pick three statistics that `-e` rejects. For each, say
   what a weighted version would mean, and why it isn't standard.
5. **Cache invalidation.** `Sample` caches `mean`, and `dev` depends on it.
   Why is it safe that nothing ever changes `Sample.x` after construction?
   What would go wrong if a statistic modified it in place?
6. **Two parsers, one file.** With `-g`, the numbers and the group keys
   come from two different parses of the same text. `read_table` checks
   that they give the same number of rows. Which rules must the two parsers
   share for that check to hold? Construct an input that would break it if
   `_split` didn't drop the text after `#`.
7. **Seeds.** `cli._seed` turns a key into an integer by putting a `1` byte
   in front of its UTF-8 bytes. Why the leading byte? (Hint: compare the keys
   `"a"` and `"\x00a"` without it.) Why is the ungrouped seed `[seed, 0]`
   and the grouped one three numbers long?
8. **A new output format.** Add `-F md` (a Markdown table). How many
   modules change? What does that say about the layering?
