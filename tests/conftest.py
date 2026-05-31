"""Shared pytest fixtures: a small offline fixture repository."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make ``src/`` importable without installation.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    """Create a tiny multi-file Python repo with refs across files."""
    (tmp_path / "utils.py").write_text(
        "def greet(name):\n"
        "    return f'hello {name}'\n\n"
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        "from utils import greet, add\n\n"
        "def run():\n"
        "    print(greet('world'))\n"
        "    return add(1, 2)\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Fixture\n", encoding="utf-8")

    # .gitignore that excludes a generated file.
    (tmp_path / ".gitignore").write_text("ignored_dir/\nsecret_notes.txt\n", encoding="utf-8")
    (tmp_path / "ignored_dir").mkdir()
    (tmp_path / "ignored_dir" / "skip.py").write_text("def skipped():\n    pass\n", encoding="utf-8")
    (tmp_path / "secret_notes.txt").write_text("do not index me\n", encoding="utf-8")

    # Secret files that must always be skipped.
    (tmp_path / ".env").write_text("API_KEY=supersecretvalue123456\n", encoding="utf-8")
    (tmp_path / "server.key").write_text("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n", encoding="utf-8")

    # A source file with a planted fake secret (file itself is allowed).
    (tmp_path / "config.py").write_text(
        "def load():\n"
        "    aws_key = 'AKIAIOSFODNN7EXAMPLE'\n"
        "    api_key = 'hunter2hunter2'\n"
        "    return aws_key\n",
        encoding="utf-8",
    )
    return tmp_path
