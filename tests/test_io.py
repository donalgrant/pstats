import numpy as np
import pytest

from stats_cli.io import DataError, ReadOptions, Table, concat, parse_columns, read_table


def test_header_autodetect():
    t = read_table("a b\n1 2\n3 4\n")
    assert t.named and t.labels == ["a", "b"]
    np.testing.assert_array_equal(t.data, [[1, 2], [3, 4]])


def test_header_after_comments():
    t = read_table("# note\n\nx y\n1 2\n")
    assert t.labels == ["x", "y"]


def test_numeric_first_line_is_data():
    t = read_table("1 2\n3 4\n")
    assert not t.named and t.labels == ["1", "2"] and t.data.shape == (2, 2)


def test_mixed_first_line_is_an_error_not_a_header():
    with pytest.raises(DataError, match="line 1"):
        read_table("a 2\n3 4\n")


def test_header_forced_and_disabled():
    assert read_table("1 2\n3 4\n", ReadOptions(header="yes")).labels == ["1", "2"]
    assert read_table("1 2\n3 4\n", ReadOptions(header="yes")).data.shape == (1, 2)
    with pytest.raises(DataError):
        read_table("a b\n1 2\n", ReadOptions(header="no"))


def test_header_only_is_no_data():
    with pytest.raises(DataError, match="after the header"):
        read_table("a b\n")


def test_csv_with_empty_fields():
    t = read_table("a,b\n1,\n,4\n5,6\n", ReadOptions(delimiter=","))
    np.testing.assert_array_equal(t.data, [[1, np.nan], [np.nan, 4], [5, 6]])


def test_csv_names_with_spaces():
    t = read_table("first col, second col\n1,2\n", ReadOptions(delimiter=","))
    assert t.labels == ["first col", "second col"]


def test_tsv():
    t = read_table("1\t2\n3\t4\n", ReadOptions(delimiter="\t"))
    assert t.data.shape == (2, 2)


@pytest.mark.parametrize(
    "spec,expected",
    [("1", [0]), ("3,1", [2, 0]), ("2-4", [1, 2, 3]), ("4-", [3, 4]), ("b,e", [1, 4])],
)
def test_parse_columns(spec, expected):
    assert parse_columns(spec, ["a", "b", "c", "d", "e"], 5) == expected


@pytest.mark.parametrize("spec", ["0", "6", "3-2", "zz", "1-9"])
def test_parse_columns_errors(spec):
    with pytest.raises(DataError):
        parse_columns(spec, ["a", "b", "c", "d", "e"], 5)


def test_column_selection_labels():
    t = read_table("1 2 3\n4 5 6\n", ReadOptions(columns="3,1"))
    assert t.labels == ["3", "1"]
    np.testing.assert_array_equal(t.data, [[3, 1], [6, 4]])


def test_column_selection_on_ragged_input():
    t = read_table("1 2 3\n4 5\n", ReadOptions(columns="3"))
    np.testing.assert_array_equal(t.data, [[3], [np.nan]])


@pytest.mark.parametrize("text", ["1 2\n3\n", "1\nNA\n", "1\nnan\n"])
def test_strict(text):
    with pytest.raises(DataError):
        read_table(text, ReadOptions(strict=True))


def test_concat_pads_and_keeps_names():
    a = Table(np.array([[1.0, 2.0]]), ["x", "y"], named=True)
    b = Table(np.array([[3.0]]), ["1"])
    warnings = []
    t = concat([a, b], warnings.append)
    assert t.labels == ["x", "y"] and t.named
    np.testing.assert_array_equal(t.data, [[1, 2], [3, np.nan]])
    assert warnings


def test_group_keys_are_text_and_excluded_from_data():
    t = read_table("band flux\nB 1\nV 2\nB 3\n", ReadOptions(group="band"))
    assert t.keys.tolist() == ["B", "V", "B"] and t.key_name == "band"
    assert t.labels == ["flux"] and t.data.shape == (3, 1)


def test_group_keys_ragged_rows():
    t = read_table("1 A\n2\n3 B\n", ReadOptions(group="2"))
    assert t.keys.tolist() == ["A", "", "B"]
    assert t.key_name == "group"


def test_text_columns_ignored_when_not_selected():
    t = read_table("name x\nfoo 1\nbar 2\n", ReadOptions(columns="x"))
    np.testing.assert_array_equal(t.data, [[1], [2]])


def test_concat_keeps_keys():
    opts = ReadOptions(group="1")
    a, b = read_table("A 1\n", opts), read_table("B 2\n", opts)
    assert concat([a, b]).keys.tolist() == ["A", "B"]


@pytest.mark.parametrize(
    "opts",
    [ReadOptions(), ReadOptions(roles={"ref": "1"}), ReadOptions(group="1")],
)
def test_wider_rows_add_columns_whatever_the_options(opts):
    t = read_table("1 2 3\n4 5\n6 7 8 9\n", opts)
    assert t.labels[-1] == "4" and t.data.shape[0] == 3


def test_group_column_text_with_ragged_rows_and_roles():
    t = read_table("band x y\nB 1 2\nV 3\nB 5 6 7\n", ReadOptions(group="band", roles={"ref": "x"}))
    assert t.keys.tolist() == ["B", "V", "B"]
    assert t.labels == ["y", "4"]
    np.testing.assert_array_equal(t.roles["ref"], [1, 3, 5])
