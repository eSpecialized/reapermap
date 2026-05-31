"""Privacy-respecting repository file scanning.

Walks a repository and yields source files to consider for the map while:

* respecting ``.gitignore`` (including nested ``.gitignore`` files) via ``pathspec``
  with early directory pruning and a practical prefix-based collector,
* skipping secret files (``.env``, ``*.pem``, ``id_rsa``, ``*.key``,
  ``credentials*``, ``.aws`` …),
* skipping binary and oversized files,
* skipping VCS / build / dependency directories (expanded SKIP list + globs,
  case-insensitive on macOS).

Reading files is also centralized here so size limits are enforced before any
content is loaded into memory.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import List, Optional, Set

try:
    import pathspec
except ImportError:  # pragma: no cover - dependency is declared in pyproject
    pathspec = None  # type: ignore

# Directories never worth scanning (case-insensitive match on macOS/Windows).
SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", "venv", ".venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "Build", ".eggs", ".tox",
    ".idea", ".vscode",
    # Xcode / Swift / Apple build artifacts (review: Derived*, .claude/worktrees, etc.)
    "DerivedData", "DerivedSources", "xcuserdata", "xcshareddata",
    "Pods", "Carthage", ".swiftpm",
    # Agent / worktree pollution
    ".claude", "worktrees",
    # Other common build / packaging / env dirs
    ".build", "target", "out", "bin", "obj",
    ".next", ".nuxt", ".svelte-kit", "coverage", ".coverage", "htmlcov",
    "tmp", "temp", "logs", ".gradle", ".mvn", "vendor", "third_party",
    ".direnv", ".devenv", "result", "dist-newstyle",
}

_SKIP_DIRS_LOWER: Set[str] = {s.lower() for s in SKIP_DIRS}

# Glob patterns for additional directory pruning (fnmatch, case-insensitive in practice).
SKIP_DIR_GLOBS: List[str] = [
    "Derived*",
    "*.xcworkspace",
    "*.xcodeproj",
    "*.build",
    "build-*",
]

# Design note on ignore strategy (defense in depth for Xcode/Swift and similar trees):
# 1. SKIP_DIRS + SKIP_DIR_GLOBS + case-folded matching: fast, unconditional prune of
#    conventional junk (build/, DerivedData/, .claude/, Pods/, etc.). Catches the
#    majority of pollution even when the project has no .gitignore or the user
#    calls with respect_gitignore=False.
# 2. .gitignore (via pathspec): user policy. We now load root + nested files,
#    rewrite nested patterns with directory prefixes, and apply the resulting
#    spec both for early *directory* pruning (huge perf win) and per-file filtering.
# 3. Secret/size/binary checks are always applied (is_secret_file, read_text, etc.).
# The combination makes the default experience much quieter on real projects
# while still allowing callers to pass explicit other_files for full control.

# Filenames / patterns that indicate secrets — always skipped.
SECRET_BASENAMES = {
    ".env",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    ".npmrc", ".pypirc", ".netrc",
}
SECRET_PREFIXES = ("credentials", ".env.")
SECRET_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks")
# ``.env.example`` is safe (no real secrets) and conventionally useful.
SECRET_ALLOWLIST = {".env.example", ".env.sample", ".env.template"}

# Skip files larger than this (bytes) to avoid loading generated/blob content.
MAX_FILE_BYTES = 1_000_000

# Cache directory created by this tool — never scan it.
TAGS_CACHE_PREFIX = ".repomap.tags.cache."


def is_secret_file(name: str) -> bool:
    """Return True if ``name`` (a basename) looks like a secret file."""
    if name in SECRET_ALLOWLIST:
        return False
    if name in SECRET_BASENAMES:
        return True
    if name.startswith(SECRET_PREFIXES):
        return True
    if name.endswith(SECRET_SUFFIXES):
        return True
    return False


def _looks_binary(path: str) -> bool:
    """Heuristically detect binary files by sniffing for NUL bytes."""
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(8192)
    except OSError:
        return True
    return b"\x00" in chunk


def _collect_gitignore_patterns(root: Path) -> List[str]:
    """Collect patterns from the root .gitignore plus all nested .gitignore files.

    Nested patterns are rewritten with a directory prefix so that a single
    PathSpec (matched against relpaths from the repo root) implements the
    intended gitignore semantics for the common case of whole-directory ignores
    (``build/``, ``DerivedData/``, etc.) placed in subdirectories.

    This is a practical, best-effort implementation rather than a perfect
    clone of git's negation/ancestor stacking rules. It is sufficient to
    respect the .gitignore files that real projects (including Xcode/Swift ones)
    actually use to hide build artifacts.
    """
    if pathspec is None:
        return []

    patterns: List[str] = []

    # Always-ignore patterns (cache + secrets) — these apply globally even if
    # the project has no .gitignore at all. They are intentionally not prefixed.
    always_patterns = [
        f"{TAGS_CACHE_PREFIX}*/",
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "id_rsa*",
        "credentials*",
    ]
    patterns.extend(always_patterns)

    # Find every .gitignore under root, using a pruned walk so we don't waste
    # time (or risk reading secrets) inside build/ or node_modules trees.
    gitignore_files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in _SKIP_DIRS_LOWER
            and not any(fnmatch.fnmatch(d, g) or fnmatch.fnmatch(d.lower(), g.lower()) for g in SKIP_DIR_GLOBS)
            and not d.startswith(TAGS_CACHE_PREFIX)
            and not (d.startswith(".") and d not in {".github"})
        ]
        if ".gitignore" in filenames:
            gitignore_files.append(Path(dirpath) / ".gitignore")

    for gi_path in gitignore_files:
        try:
            lines = gi_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        # Compute the directory prefix for this .gitignore (relative to root).
        try:
            rel_dir = gi_path.parent.relative_to(root)
            prefix = str(rel_dir).replace(os.sep, "/") if str(rel_dir) != "." else ""
        except ValueError:
            prefix = ""

        for raw in lines:
            p = raw.strip()
            if not p or p.startswith("#"):
                continue
            is_neg = p.startswith("!")
            if is_neg:
                p = p[1:].strip()
            if p.startswith("/"):
                p = p[1:]
            if prefix:
                # Prefix subdir patterns. Keep **/ patterns as-is (they are already global-ish).
                if not p.startswith("**/"):
                    p = f"{prefix}/{p}"
            if is_neg:
                p = "!" + p
            patterns.append(p)

    return patterns


def _load_gitignore(root: Path) -> Optional["pathspec.PathSpec"]:
    """Load gitignore patterns from the repo root and all nested .gitignore files.

    Returns a single PathSpec that can be used with relpaths from ``root``.
    The collected patterns include the project's own ignores plus our own
    always-ignore rules for the tags cache and common secret files.
    """
    if pathspec is None:
        return None
    patterns = _collect_gitignore_patterns(root)
    if not patterns:
        return None
    return pathspec.PathSpec.from_lines("gitignore", patterns)


def find_src_files(directory: str, respect_gitignore: bool = True) -> List[str]:
    """Return absolute paths of scannable source files under ``directory``.

    Single files are returned directly (after the secret check). Directories
    are walked with the skip rules above applied, including ``.gitignore``
    (root + nested, with directory pruning), the expanded SKIP list + globs
    (Xcode, build, worktree, etc., case-folded), binary sniffing, the size cap,
    secret files, and the local repo-map cache directory. This is the main
    discovery boundary used by the CLI and MCP server.
    """
    if os.path.isfile(directory):
        name = os.path.basename(directory)
        if is_secret_file(name):
            return []
        return [os.path.abspath(directory)]

    if not os.path.isdir(directory):
        return []

    root = Path(directory).resolve()
    spec = _load_gitignore(root) if respect_gitignore else None

    src_files: List[str] = []
    for current, dirs, files in os.walk(root):
        # Prune skip dirs and hidden dirs (but keep walking the root itself).
        # Case-folded + glob support catches macOS Xcode "Build/", "DerivedData", etc.
        # Also prune directories matched by .gitignore (root + nested via the spec)
        # so we never descend into huge ignored build/ or DerivedData/ trees.
        kept_dirs: List[str] = []
        for d in dirs:
            if d.lower() in _SKIP_DIRS_LOWER:
                continue
            if any(fnmatch.fnmatch(d, g) or fnmatch.fnmatch(d.lower(), g.lower()) for g in SKIP_DIR_GLOBS):
                continue
            if d.startswith(TAGS_CACHE_PREFIX):
                continue
            if d.startswith(".") and d not in {".github"}:
                continue
            if spec is not None:
                rel = os.path.relpath(os.path.join(current, d), root).replace(os.sep, "/")
                if spec.match_file(rel) or spec.match_file(rel + "/"):
                    continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        for fname in files:
            if is_secret_file(fname):
                continue
            abs_path = os.path.join(current, fname)
            rel_path = os.path.relpath(abs_path, root)

            if spec is not None and spec.match_file(rel_path):
                continue

            try:
                if os.path.getsize(abs_path) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue

            if _looks_binary(abs_path):
                continue

            src_files.append(abs_path)

    return src_files


def read_text(filename: str, encoding: str = "utf-8", silent: bool = True) -> Optional[str]:
    """Read text from ``filename`` with size and error guards.

    Returns ``None`` on any failure (missing, too large, decode error). Secret
    files are refused even if requested directly. Repository content reads are
    routed through this helper by default so scanner and parser paths share the
    same privacy limits.
    """
    name = os.path.basename(filename)
    if is_secret_file(name):
        return None
    try:
        if os.path.getsize(filename) > MAX_FILE_BYTES:
            return None
        return Path(filename).read_text(encoding=encoding, errors="ignore")
    except (FileNotFoundError, IsADirectoryError, OSError, UnicodeError):
        if not silent:
            print(f"Error reading {filename}")
        return None
