"""Security regression tests using the committed mockrepotest fixture."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from privrepomap.cli import main as cli_main
from privrepomap.filescan import find_src_files, read_text
from privrepomap.repomap import RepoMap
from privrepomap.server import repo_map, search_identifiers


REPO_ROOT = Path(__file__).resolve().parents[1]
MOCK_SOURCE = REPO_ROOT / "mockrepotest"
CANARY_RE = re.compile(r"MOCKREPOTEST[0-9A-Za-z_-]*")


def _copy_mock_repo(tmp_path: Path) -> Path:
    target = tmp_path / "mockrepotest"
    shutil.copytree(MOCK_SOURCE, target)
    return target


def _collect_canaries(root: Path) -> set[str]:
    canaries: set[str] = set()
    for path in root.rglob("*"):
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            canaries.update(CANARY_RE.findall(text))
    return canaries


def _assert_no_mock_leaks(obj, canaries: set[str]) -> None:
    text = json.dumps(obj, sort_keys=True) if not isinstance(obj, str) else obj
    leaked = sorted(canary for canary in canaries if canary in text)
    assert leaked == []


def _mapper(root: Path) -> RepoMap:
    return RepoMap(
        map_tokens=8192,
        root=str(root),
        file_reader_func=read_text,
        output_handler_funcs={
            "info": lambda *a: None,
            "warning": lambda *a: None,
            "error": lambda *a: None,
        },
    )


def test_mockrepotest_scan_excludes_secret_and_ignored_paths(tmp_path):
    repo = _copy_mock_repo(tmp_path)
    files = find_src_files(str(repo))
    rels = {Path(f).relative_to(repo).as_posix() for f in files}

    assert "src/app.py" in rels
    assert "src/config.py" in rels
    assert ".env.example" in rels
    assert ".env" not in rels
    assert ".env.production" not in rels
    assert ".npmrc" not in rels
    assert ".pypirc" not in rels
    assert ".netrc" not in rels
    assert "id_rsa" not in rels
    assert "server.pem" not in rels
    assert "credentials.json" not in rels
    assert "secrets/app.key" not in rels
    assert not any(rel.startswith("ignored_secrets/") for rel in rels)
    assert not any(rel.startswith("generated/") for rel in rels)
    assert not any(rel.startswith("nested/ignored/") for rel in rels)
    assert not any(rel.startswith("build/") for rel in rels)
    assert not any(rel.startswith("DerivedData/") for rel in rels)
    assert not any(rel.startswith("node_modules/") for rel in rels)
    assert not any(rel.startswith(".claude/") for rel in rels)


def test_mockrepotest_direct_secret_reads_are_refused(tmp_path):
    repo = _copy_mock_repo(tmp_path)

    for rel in [
        ".env",
        ".env.production",
        ".npmrc",
        ".pypirc",
        ".netrc",
        "id_rsa",
        "server.pem",
        "credentials.json",
        "secrets/app.key",
    ]:
        assert read_text(str(repo / rel)) is None


def test_mockrepotest_repo_map_does_not_leak_canaries(tmp_path):
    repo = _copy_mock_repo(tmp_path)
    canaries = _collect_canaries(repo)
    mapper = _mapper(repo)
    files = find_src_files(str(repo))

    map_content, report = mapper.get_repo_map(
        other_files=files,
        mentioned_idents={"load_settings", "processFixture"},
    )

    assert map_content is not None
    assert "src/app.py" in map_content
    assert "load_settings" in map_content
    assert report.total_files_considered > 0
    _assert_no_mock_leaks(map_content, canaries)


def test_mockrepotest_identifier_search_does_not_leak_context_canaries(tmp_path):
    repo = _copy_mock_repo(tmp_path)
    canaries = _collect_canaries(repo)

    result = asyncio.run(
        search_identifiers(
            project_root=str(repo),
            query="load_settings",
            max_results=10,
            context_lines=30,
            include_definitions=True,
            include_references=True,
            force_refresh=True,
        )
    )

    assert "error" not in result
    assert result["results"]
    _assert_no_mock_leaks(result, canaries)


def test_mockrepotest_mcp_repo_map_does_not_leak_canaries(tmp_path):
    repo = _copy_mock_repo(tmp_path)
    canaries = _collect_canaries(repo)

    result = asyncio.run(
        repo_map(
            project_root=str(repo),
            token_limit=8192,
            mentioned_idents=["load_settings", "processFixture"],
            force_refresh=True,
        )
    )

    assert "error" not in result
    assert "src/app.py" in result["map"]
    _assert_no_mock_leaks(result, canaries)


def test_mockrepotest_cli_does_not_leak_canaries(tmp_path, capsys):
    repo = _copy_mock_repo(tmp_path)
    canaries = _collect_canaries(repo)

    exit_code = cli_main([
        "--root",
        str(repo),
        "--map-tokens",
        "8192",
        "--mentioned-idents",
        "load_settings",
        "processFixture",
        str(repo),
    ])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "src/app.py" in captured.out
    _assert_no_mock_leaks(captured.out, canaries)
    _assert_no_mock_leaks(captured.err, canaries)


def test_mockrepotest_cli_subprocess_does_not_leak_canaries(tmp_path):
    repo = _copy_mock_repo(tmp_path)
    canaries = _collect_canaries(repo)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "privrepomap.cli",
            "--root",
            str(repo),
            "--map-tokens",
            "8192",
            "--mentioned-idents",
            "load_settings",
            "processFixture",
            str(repo),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "src/app.py" in result.stdout
    _assert_no_mock_leaks(result.stdout, canaries)
    _assert_no_mock_leaks(result.stderr, canaries)

