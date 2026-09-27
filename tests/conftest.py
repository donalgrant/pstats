import io
from pathlib import Path

import pytest

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden"


@pytest.fixture
def run(monkeypatch, capsys):
    """Run ``stats`` in-process: run(args, stdin) -> (exit code, stdout, stderr)."""
    from stats_cli.cli import main

    def _run(args, stdin=""):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        code = main(args)
        out, err = capsys.readouterr()
        return code, out, err

    return _run
