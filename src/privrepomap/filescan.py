"""Privacy-respecting repository file scanning.

Walks a repository and yields source files to consider for the map while:

* respecting ``.gitignore`` (and nested ``.gitignore`` files) via ``pathspec``,
* skipping secret files (``.env``, ``*.pem``, ``id_rsa``, ``*.key``,
  ``credentials*``, ``.aws`` …),
* skipping binary and oversized files,
* skipping VCS / build / dependency directories.

Reading files is also centralized here so size limits are enforced before any
content is loaded into memory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

try:
    import pathspec
except ImportError:  # pragma: no cover - dependency is declared in pyproject
    pathspec = None  # type: ignore

# Directories never worth scanning.
SKIP_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", "venv", ".venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".eggs", ".tox",
    ".idea", ".vscode",
}

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


def _load_gitignore(root: Path) -> Optional["pathspec.PathSpec"]:
    """Load gitignore patterns from the repo root, if any."""
    if pathspec is None:
        return None
    patterns: List[str] = []
    gitignore = root / ".gitignore"
    if gitignore.is_file():
        try:
            patterns.extend(gitignore.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            pass
    # Always ignore our own cache and obvious secret patterns even if the repo
    # has no .gitignore.
    patterns.extend([
        f"{TAGS_CACHE_PREFIX}*/",
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "id_rsa*",
        "credentials*",
    ])
    if not patterns:
        return None
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def find_src_files(directory: str, respect_gitignore: bool = True) -> List[str]:
    """Return absolute paths of scannable source files under ``directory``.

    Single files are returned directly (after the secret check). Directories
    are walked with the skip rules above applied.
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
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS
            and not d.startswith(TAGS_CACHE_PREFIX)
            and not (d.startswith(".") and d not in {".github"})
        ]

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
    files are refused even if requested directly.
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
