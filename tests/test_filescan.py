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


def test_expanded_skip_dirs_and_globs_prune_xcode_artifacts(tmp_path):
    """Verify the expanded SKIP list + globs catch real-world Xcode / build pollution (case variants too)."""
    # Create a realistic polluted tree
    src_file = tmp_path / "src" / "main.swift"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("func main() {}", encoding="utf-8")

    # Various artifact dirs that must be completely invisible
    for junk in [
        "build",
        "Build",           # macOS case-preserving variant
        "DerivedData/Logs/Stuff",
        "Pods/SomePod",
        ".claude/worktrees/abc123/src",
        "MyApp.xcodeproj/project.pbxproj",
        "MyApp.xcworkspace/contents.xcworkspacedata",
        "Packages/MyLib/build/artifact.o",
    ]:
        p = tmp_path / junk
        if p.suffix:  # treat as file (e.g. pbxproj inside the bundle dir)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("junk", encoding="utf-8")
        else:
            p.mkdir(parents=True, exist_ok=True)
            (p / "dummy.txt").write_text("junk", encoding="utf-8")

    files = find_src_files(str(tmp_path))
    rels = {os.path.relpath(f, tmp_path) for f in files}

    assert "src/main.swift" in rels
    # None of the artifact trees should appear
    assert not any(r.startswith("build") or r.startswith("Build") for r in rels)
    assert not any("DerivedData" in r for r in rels)
    assert not any("Pods" in r for r in rels)
    assert not any(".claude" in r for r in rels)
    assert not any("xcodeproj" in r or "xcworkspace" in r for r in rels)
    assert not any("Packages/MyLib/build" in r for r in rels)


def test_nested_gitignore_is_respected(tmp_path):
    """A .gitignore in a subdirectory should hide files under that subtree."""
    real_py = tmp_path / "src" / "real.py"
    real_py.parent.mkdir(parents=True)
    real_py.write_text("x = 1", encoding="utf-8")

    # Root .gitignore ignores one top-level thing
    (tmp_path / ".gitignore").write_text("top_level_ignored/\n", encoding="utf-8")
    top_ignored = tmp_path / "top_level_ignored" / "skip.txt"
    top_ignored.parent.mkdir(parents=True)
    top_ignored.write_text("no", encoding="utf-8")

    # Nested package has its own build/ ignore
    nested_gi = tmp_path / "Packages" / "MyLib" / ".gitignore"
    nested_gi.parent.mkdir(parents=True)
    nested_gi.write_text("build/\n", encoding="utf-8")
    # Create a build/ dir that the nested .gitignore should hide (no files from it should appear)
    (tmp_path / "Packages" / "MyLib" / "build").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Packages" / "MyLib" / "build" / "artifact.o").write_text("no", encoding="utf-8")

    lib_swift = tmp_path / "Packages" / "MyLib" / "src" / "lib.swift"
    lib_swift.parent.mkdir(parents=True)
    lib_swift.write_text("func f() {}", encoding="utf-8")

    files = find_src_files(str(tmp_path))
    rels = {os.path.relpath(f, tmp_path) for f in files}

    assert "src/real.py" in rels
    assert "Packages/MyLib/src/lib.swift" in rels
    # Both the root ignore and the nested one must have taken effect
    assert "top_level_ignored/skip.txt" not in rels
    assert "Packages/MyLib/build/artifact.o" not in rels


def test_respect_gitignore_false_still_applies_skip_and_secrets(tmp_path):
    """respect_gitignore=False must not leak SKIP dirs or secrets."""
    (tmp_path / "real.py").write_text("print(1)", encoding="utf-8")
    build_junk = tmp_path / "build" / "junk.o"
    build_junk.parent.mkdir(parents=True)
    build_junk.write_text("no", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")

    files = find_src_files(str(tmp_path), respect_gitignore=False)
    basenames = {os.path.basename(f) for f in files}

    assert "real.py" in basenames
    assert "junk.o" not in basenames          # SKIP still wins
    assert ".env" not in basenames            # secret check is unconditional
