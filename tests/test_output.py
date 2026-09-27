import json

from stats_cli.output import OutputOptions, render

STATS = ["n", "mean"]
COLS = ["a", "b"]
VALUES = [[3.0, 2.5], [3.0, 1 / 3]]


def test_default_table_matches_original_layout():
    out = render(STATS, COLS, VALUES, OutputOptions())
    assert out.splitlines() == [
        "         n       mean",
        "         3        2.5",
        "         3     0.3333",
    ]


def test_labels():
    out = render(STATS, COLS, VALUES, OutputOptions(labels=True))
    assert out.splitlines()[0].startswith("column ")
    assert out.splitlines()[1].startswith("a ")


def test_transpose():
    out = render(STATS, COLS, VALUES, OutputOptions(transpose=True, labels=True))
    lines = out.splitlines()
    assert lines[0].split() == ["stat", "a", "b"]
    assert lines[2].split() == ["mean", "2.5", "0.3333"]


def test_transpose_without_labels_has_no_header():
    out = render(STATS, COLS, VALUES, OutputOptions(transpose=True))
    assert [line.split()[0] for line in out.splitlines()] == ["n", "mean"]


def test_csv_full_precision():
    out = render(STATS, COLS, VALUES, OutputOptions(format="csv", labels=True))
    assert out.splitlines() == ["column,n,mean", "a,3,2.5", f"b,3,{1 / 3!r}"]


def test_tsv_no_header():
    out = render(STATS, COLS, VALUES, OutputOptions(format="tsv", header=False))
    assert out.splitlines() == ["3\t2.5", f"3\t{1 / 3!r}"]


def test_json_nan_is_null():
    out = json.loads(render(STATS, ["a"], [[0.0, float("nan")]], OutputOptions(format="json")))
    assert out == [{"column": "a", "n": 0, "mean": None}]


def test_precision_and_printf():
    assert "0.33333333" in render(STATS, COLS, VALUES, OutputOptions(precision=8))
    assert "0.333" in render(STATS, COLS, VALUES, OutputOptions(printf="%.3f"))


def test_wide_values_keep_alignment():
    out = render(["x"], ["a", "b"], [[1.0], [-1.234567e-100]], OutputOptions(precision=6))
    widths = {len(line) for line in out.splitlines()}
    assert len(widths) == 1


def test_json_transpose():
    out = json.loads(render(STATS, COLS, VALUES, OutputOptions(format="json", transpose=True)))
    assert out == [{"stat": "n", "a": 3, "b": 3}, {"stat": "mean", "a": 2.5, "b": 1 / 3}]


def test_json_transpose_grouped_labels():
    out = json.loads(
        render(
            ["n"],
            [("B", "x"), ("V", "x")],
            [[1.0], [2.0]],
            OutputOptions(format="json", transpose=True),
            ("band", "column"),
        )
    )
    assert out == [{"stat": "n", "B:x": 1, "V:x": 2}]
