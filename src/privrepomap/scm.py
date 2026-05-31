"""Language -> tree-sitter tags query (``.scm``) file resolution.

Query files are bundled in the repository ``queries/`` directory, split into
``tree-sitter-language-pack`` and ``tree-sitter-languages`` collections. They
are local data files; no network access is involved.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Languages with a bundled tags query. The value is the ``.scm`` filename.
SCM_FILES = {
    "arduino": "arduino-tags.scm",
    "chatito": "chatito-tags.scm",
    "commonlisp": "commonlisp-tags.scm",
    "cpp": "cpp-tags.scm",
    "csharp": "csharp-tags.scm",
    "c": "c-tags.scm",
    "dart": "dart-tags.scm",
    "d": "d-tags.scm",
    "elisp": "elisp-tags.scm",
    "elixir": "elixir-tags.scm",
    "elm": "elm-tags.scm",
    "gleam": "gleam-tags.scm",
    "go": "go-tags.scm",
    "javascript": "javascript-tags.scm",
    "java": "java-tags.scm",
    "lua": "lua-tags.scm",
    "ocaml_interface": "ocaml_interface-tags.scm",
    "ocaml": "ocaml-tags.scm",
    "pony": "pony-tags.scm",
    "properties": "properties-tags.scm",
    "python": "python-tags.scm",
    "racket": "racket-tags.scm",
    "r": "r-tags.scm",
    "ruby": "ruby-tags.scm",
    "rust": "rust-tags.scm",
    "solidity": "solidity-tags.scm",
    "swift": "swift-tags.scm",
    "udev": "udev-tags.scm",
    "c_sharp": "c_sharp-tags.scm",
    "hcl": "hcl-tags.scm",
    "kotlin": "kotlin-tags.scm",
    "php": "php-tags.scm",
    "ql": "ql-tags.scm",
    "scala": "scala-tags.scm",
    "typescript": "typescript-tags.scm",
}

# Collections searched in order of preference.
_COLLECTIONS = ("tree-sitter-language-pack", "tree-sitter-languages")


def _queries_root() -> Optional[Path]:
    """Locate the bundled ``queries/`` directory.

    Honors the ``PRIVREPOMAP_QUERIES`` environment variable, otherwise
    searches upward from this file for a ``queries`` directory.
    """
    env = os.environ.get("PRIVREPOMAP_QUERIES")
    if env:
        p = Path(env)
        if p.is_dir():
            return p

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "queries"
        if candidate.is_dir():
            return candidate
    return None


def get_scm_fname(lang: str) -> Optional[str]:
    """Return the local tags-query path for ``lang``, or ``None``.

    Resolution uses bundled query files or the trusted ``PRIVREPOMAP_QUERIES``
    override. It never downloads query data.
    """
    scm_filename = SCM_FILES.get(lang)
    if not scm_filename:
        return None

    root = _queries_root()
    if root is None:
        return None

    for collection in _COLLECTIONS:
        scm_path = root / collection / scm_filename
        if scm_path.exists():
            return str(scm_path)
    return None
