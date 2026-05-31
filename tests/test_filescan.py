"""Filescan privacy tests: gitignore respected, secret files skipped."""

import os

from privrepomap.filescan import find_src_files, is_secret_file, read_text


def test_secret_basename_detection():
    assert is_secret_file(".env")
    assert is_secret_file(".env.production")
    assert is_secret_file("server.pem")
    assert is_secret_file("id_rsa")
    assert is_secret_file("credentials.json")
    assert not is_secret_file(".env.example")
    assert not is_secret_file("main.py")


def test_gitignore_respected(fixture_repo):
    files = find_src_files(str(fixture_repo))
    names = {os.path.relpath(f, fixture_repo) for f in files}
    assert "ignored_dir/skip.py" not in names
    assert "secret_notes.txt" not in names
    assert "utils.py" in names
    assert "main.py" in names


def test_secret_files_skipped(fixture_repo):
    files = find_src_files(str(fixture_repo))
    basenames = {os.path.basename(f) for f in files}
    assert ".env" not in basenames
    assert "server.key" not in basenames


def test_read_text_refuses_secret(fixture_repo):
    assert read_text(str(fixture_repo / ".env")) is None
    assert read_text(str(fixture_repo / "utils.py")) is not None
