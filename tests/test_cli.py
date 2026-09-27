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
