"""Every ```console example in the README and docs/ runs and prints what it shows.

A console block is a series of "$ command" lines, each followed by its
expected output (stdout; examples that show an error use ``2>&1``). A block
preceded by an HTML comment ``<!-- file: NAME -->`` is written to the file
NAME before the examples after it run. The commands of a block run in one
bash shell, in a temporary directory shared by the blocks of a document,
with the package's commands on the PATH. Trailing spaces are ignored.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
MARK = "@@command-"
BLOCK = re.compile(
    r"(?:<!-- file: (\S+) -->\n)?^```(console|\w*)\n(.*?)^```", re.MULTILINE | re.DOTALL
)


def blocks():
    """(document, files to write, console block) for each console block, in order."""
    for doc in DOCS:
        files: dict[str, str] = {}
        n = 0
        for m in BLOCK.finditer(doc.read_text(encoding="utf-8")):
            name, kind, body = m.groups()
            if name:
                files[name] = body
            elif kind == "console":
                n += 1
                yield pytest.param(doc.name, dict(files), body, id=f"{doc.name}-{n}")


def steps(block: str) -> list[tuple[str, list[str]]]:
    """(command, expected output lines) pairs."""
    out: list[tuple[str, list[str]]] = []
    for line in block.splitlines():
        if line.startswith("$ "):
            out.append((line[2:], []))
        elif out:
            out[-1][1].append(line.rstrip())
    for _, expected in out:  # a blank line between examples isn't output
        while expected and not expected[-1]:
            expected.pop()
    return out


@pytest.fixture(scope="module")
def workdirs(tmp_path_factory):
    return {doc.name: tmp_path_factory.mktemp(doc.stem) for doc in DOCS}


@pytest.mark.parametrize("doc,files,block", list(blocks()))
def test_console_example(doc, files, block, workdirs):
    workdir = workdirs[doc]
    for name, text in files.items():
        (workdir / name).write_text(text, encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "COLUMNS": "80",  # histogram bars fit the terminal width
        "LC_ALL": "C.UTF-8",
    }
    # Run the block's commands in one shell, as a reader would type them, so
    # variables carry over; a marker line before each command splits the output.
    commands = steps(block)
    script = "".join(f"echo '{MARK}{i}'\n{command}\n" for i, (command, _) in enumerate(commands))
    p = subprocess.run(
        ["bash", "-c", script], cwd=workdir, env=env, capture_output=True, text=True, check=False
    )
    outputs = re.split(rf"^{MARK}\d+\n", p.stdout, flags=re.MULTILINE)[1:]
    assert len(outputs) == len(commands), p.stderr
    for (command, expected), out in zip(commands, outputs, strict=True):
        got = [line.rstrip() for line in out.splitlines()]
        while got and not got[-1]:
            got.pop()
        assert got == expected, f"$ {command}\n{p.stderr}"
