import pytest

from stats_cli.findgen import main


@pytest.mark.parametrize(
    "args,expected",
    [
        (["3"], [0, 1, 2]),
        (["3", "-o", "1"], [1, 2, 3]),
        (["3", "-o", "1", "-r"], [3, 2, 1]),
        (["4", "-s", "5"], [0, 5, 10, 15]),
        (["3", "-s", "-1"], [0, -1, -2]),
        (["0"], []),
    ],
)
def test_findgen(capsys, args, expected):
    assert main(args) == 0
    assert [int(v) for v in capsys.readouterr().out.split()] == expected


def test_zero_step_rejected():
    with pytest.raises(SystemExit):
        main(["3", "-s", "0"])
