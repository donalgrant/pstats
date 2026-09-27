import pytest

from stats_cli.cli import EXIT_DATA, EXIT_USAGE


def test_basic(run):
    code, out, err = run(["n", "mean"], "1\n2\n3\n")
    assert code == 0 and err == ""
    assert out.splitlines() == ["         n       mean", "         3          2"]


def test_multiple_columns_one_row_each(run):
    code, out, _ = run(["-nh", "sum"], "1 10\n2 20\n")
    assert out.split() == ["3", "30"]


def test_comments_and_blank_lines_ignored(run):
    code, out, _ = run(["-nh", "n"], "# header\n1\n\n2  # note\n")
    assert out.split() == ["2"]


def test_ragged_rows_padded_with_warning(run):
    code, out, err = run(["-nh", "n"], "1 2\n3\n4 5\n")
    assert code == 0 and out.split() == ["3", "2"]
    assert "warning" in err


def test_quiet_suppresses_warnings(run):
    _, _, err = run(["-q", "n"], "1 2\n3\n")
    assert err == ""


def test_nan_tokens(run):
    _, out, _ = run(["-nh", "n", "mean"], "1\nNA\n3\n")
    assert out.split() == ["2", "2"]


def test_non_numeric_is_data_error(run):
    code, out, err = run(["mean"], "1\nabc\n")
    assert code == EXIT_DATA and out == "" and "line 2" in err


def test_empty_input_is_data_error(run):
    code, _, err = run(["mean"], "")
    assert code == EXIT_DATA and "no input" in err


@pytest.mark.parametrize("args", [[], ["bogus"], ["qN"], ["q200"]])
def test_usage_errors_go_to_stderr(run, args):
    code, out, err = run(args, "1\n")
    assert code == EXIT_USAGE and out == "" and "error" in err


def test_list_stats(run):
    for flag in ["--list-stats", "--stat_list", "-l"]:
        code, out, _ = run([flag])
        assert code == 0 and "qN" in out and "stdev" in out


def test_verbose_goes_to_stderr(run):
    _, out, err = run(["-v", "-nh", "n"], "1\n2\n")
    assert out.split() == ["2"] and "rows" in err


def test_help_and_version(run):
    for flag in ["--help", "--version"]:
        with pytest.raises(SystemExit) as e:
            run([flag])
        assert e.value.code == 0


def test_file_arguments(run, tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("1\n2\n")
    b.write_text("3\n")
    code, out, _ = run(["-nh", "n", "sum", "-f", str(a), "-f", str(b)])
    assert code == 0 and out.split() == ["3", "6"]


def test_stdin_dash_with_file(run, tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("1\n")
    _, out, _ = run(["-nh", "n", "-f", "-", "-f", str(a)], "5\n6\n")
    assert out.split() == ["3"]


def test_missing_file(run):
    code, _, err = run(["mean", "-f", "does-not-exist.txt"])
    assert code == EXIT_DATA and "does-not-exist.txt" in err


def test_csv_header_gives_labels(run):
    code, out, _ = run(["--csv", "mean"], "x,y\n1,2\n3,4\n")
    assert out.splitlines()[1].split() == ["x", "2"]


def test_columns_by_name_and_labels_off(run):
    _, out, _ = run(["--csv", "-c", "y", "--no-labels", "-nh", "mean"], "x,y\n1,2\n3,4\n")
    assert out.split() == ["3"]


def test_force_labels(run):
    _, out, _ = run(["-L", "-nh", "n"], "1 2\n")
    assert [line.split() for line in out.splitlines()] == [["1", "1"], ["2", "1"]]


def test_options_after_stats(run):
    _, out, _ = run(["mean", "-nh", "n"], "1\n2\n")
    assert out.split() == ["1.5", "2"]


def test_json_output(run):
    import json

    _, out, _ = run(["-F", "json", "n"], "1\n2\n")
    assert json.loads(out) == [{"column": "1", "n": 2}]


def test_strict_flag(run):
    code, _, err = run(["--strict", "n"], "1 2\n3\n")
    assert code == EXIT_DATA and "strict" in err


@pytest.mark.parametrize("args", [["--fmt", "%d%d", "n"], ["-p", "0", "n"], ["-d", "ab", "n"]])
def test_bad_output_options(run, args):
    code, _, err = run(args, "1\n")
    assert code == EXIT_USAGE and "error" in err


def test_conflicting_delimiters(run):
    with pytest.raises(SystemExit) as e:
        run(["--csv", "--tsv", "n"], "1\n")
    assert e.value.code == EXIT_USAGE


XY = "x y z\n1 2.1 9\n2 3.9 7\n3 6.2 6\n4 7.8 2\n"


def test_reference_column_rows_and_labels(run):
    code, out, _ = run(["-x", "x", "corr", "slope"], XY)
    lines = out.splitlines()
    assert code == 0 and lines[0].split() == ["column", "corr", "slope"]
    assert [line.split()[0] for line in lines[1:]] == ["y", "z"]


def test_reference_by_number_with_plain_stats(run):
    _, out, _ = run(["-x", "1", "-nh", "n", "slope"], "1 2\n2 4\n3 6\n")
    assert out.split() == ["2", "3", "2"]


def test_cross_stat_without_reference(run):
    code, _, err = run(["corr"], XY)
    assert code == EXIT_USAGE and "-x" in err


def test_weights_column_excluded_and_applied(run):
    _, out, _ = run(["-w", "2", "-nh", "n", "mean"], "1 3\n5 1\n")
    assert out.split() == ["1", "4", "2"]


def test_errors_column(run):
    _, out, _ = run(["-e", "2", "-nh", "mean", "stderr"], "10 1\n20 1\n")
    assert [float(v) for v in out.split()[1:]] == [15, pytest.approx(0.7071, rel=1e-3)]


@pytest.mark.parametrize(
    "args,msg",
    [
        (["-e", "2", "median"], "-w for frequency weights"),
        (["-w", "2", "trimmean10"], "does not support weights"),
        (["chi2"], "requires measurement errors"),
        (["-w", "2", "chi2"], "requires measurement errors"),
        (["-w", "1", "-e", "2", "n"], None),
    ],
)
def test_weight_mode_errors(run, args, msg):
    if msg is None:
        with pytest.raises(SystemExit):
            run(args, "1 2\n")
        return
    code, _, err = run(args, "1 2\n3 4\n")
    assert code == EXIT_USAGE and msg in err


@pytest.mark.parametrize("args", [["-w", "2", "n"], ["-e", "2", "n"]])
def test_bad_weight_values(run, args):
    code, _, err = run(args, "1 -1\n2 1\n")
    assert code == EXIT_DATA


def test_matrix(run):
    code, out, _ = run(["--matrix", "corr"], XY)
    lines = out.splitlines()
    assert code == 0 and lines[0].split() == ["column", "x", "y", "z"]
    assert lines[1].split()[:2] == ["x", "1"]


@pytest.mark.parametrize("args", [["--matrix", "corr", "mean"], ["--matrix", "cov", "-x", "1"]])
def test_matrix_conflicts(run, args):
    code, _, _ = run(args, XY)
    assert code == EXIT_USAGE


def test_role_must_be_single_column(run):
    code, _, err = run(["-x", "1-2", "corr"], XY)
    assert code == EXIT_DATA and "single column" in err


def test_list_stats_sections(run):
    _, out, _ = run(["-l"])
    assert "need -x" in out and "slope_err" in out and "trimmeanN" in out
