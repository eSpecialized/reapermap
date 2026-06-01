"""Tests for caller-supplied scan narrowing: globs and source-only mode."""

from pathlib import Path

from privrepomap.filescan import find_src_files


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "engine.py").write_text("def run():\n    pass\n", encoding="utf-8")
    (tmp_path / "src" / "helper.js").write_text("function help() {}\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_engine.py").write_text("def test_run():\n    pass\n", encoding="utf-8")
    (tmp_path / "Widget.swift").write_text("class Widget {}\n", encoding="utf-8")
    (tmp_path / "WidgetTests.swift").write_text("class WidgetTests {}\n", encoding="utf-8")
    return tmp_path


def _rel(root: Path, files):
    return {str(Path(f).relative_to(root)).replace("\\", "/") for f in files}


def test_include_globs_restrict_scope(tmp_path):
    repo = _make_repo(tmp_path)
    files = _rel(repo, find_src_files(str(repo), include_globs=["*.py"]))
    assert files == {"src/engine.py", "tests/test_engine.py"}


def test_exclude_globs_drop_files(tmp_path):
    repo = _make_repo(tmp_path)
    files = _rel(repo, find_src_files(str(repo), exclude_globs=["*.swift"]))
    assert "Widget.swift" not in files
    assert "WidgetTests.swift" not in files
    assert "src/engine.py" in files


def test_source_only_excludes_tests(tmp_path):
    repo = _make_repo(tmp_path)
    files = _rel(repo, find_src_files(str(repo), source_only=True))
    assert "Widget.swift" in files
    assert "src/engine.py" in files
    assert "WidgetTests.swift" not in files
    assert "tests/test_engine.py" not in files


def test_default_scan_includes_everything(tmp_path):
    repo = _make_repo(tmp_path)
    files = _rel(repo, find_src_files(str(repo)))
    assert {"src/engine.py", "src/helper.js", "tests/test_engine.py",
            "Widget.swift", "WidgetTests.swift"} <= files


def test_source_only_on_single_test_file(tmp_path):
    repo = _make_repo(tmp_path)
    assert find_src_files(str(repo / "WidgetTests.swift"), source_only=True) == []
    assert find_src_files(str(repo / "Widget.swift"), source_only=True)
