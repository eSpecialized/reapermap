# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`privrepomap` is a **private, offline, structural** repository mapper: it produces a
token-budgeted map of a codebase (function/class signatures + most relevant files)
using tree-sitter parsing and PageRank ranking. It ships as a CLI (`privrepomap`) and
an MCP server (`privrepomap-mcp`), and is intended as an offline replacement for cloud
`semantic_search`. Clean-room reimplementation inspired by RepoMapper and Aider's repo
map (see `NOTICE`).

The package name is `privrepomap`; the repo directory is `reapermap`.

## Commands

```bash
# Setup (editable install into a venv)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[test]"

# Run CLI
privrepomap .                              # map cwd, 8192-token budget
privrepomap src/ --map-tokens 2048
privrepomap . --chat-files src/app/main.py --mentioned-idents handleClick

# Run MCP server (stdio)
privrepomap-mcp

# Tests
pytest -q
pytest tests/test_repomap.py -q            # single file
pytest tests/test_offline.py::test_map_generation_offline   # single test
```

There is no linter or build step configured; this is a pure-Python `setuptools` package.

## The hard privacy constraint

**The core invariant is: zero network access, zero telemetry.** Every design choice
flows from this, and it is enforced by `tests/test_offline.py`, which monkeypatches
`socket` so any connection attempt fails the suite. When changing dependencies or
adding code, do not introduce anything that touches the network at import or runtime.

Concrete consequences to preserve:
- **No `tiktoken`.** Token counting is a local estimate in `tokenizer.py` (heuristic
  ~4 chars/token, or a Pygments-lexer count). `tiktoken` downloads its vocab on first
  use, so it is intentionally excluded from `pyproject.toml`.
- **Telemetry env vars are set before importing FastMCP** in `server.py`
  (`FASTMCP_DISABLE_TELEMETRY`, `DO_NOT_TRACK`, `ANONYMIZED_TELEMETRY`). Keep that
  ordering — they must be set prior to the `from fastmcp import ...` line.
- **Secrets are handled at three layers** (defense in depth): `filescan.py` refuses to
  read secret files (`.env`, `*.pem`, `id_rsa*`, `credentials*`, …) even when requested
  directly; output is run through regex redaction in `redact.py` before leaving the
  process; and the tags cache stays local and gitignored.

## Architecture / data flow

The map is built by a pipeline; `repomap.py` (`RepoMap`) is the orchestrator and the
file to read first.

1. **`filescan.py`** — walks the repo, returns scannable source files. Applies
   `.gitignore` (via `pathspec`), skip-dirs, secret-file rules, size cap
   (`MAX_FILE_BYTES`), and binary sniffing. `read_text()` is the single choke point for
   reading file content and re-enforces the secret/size guards.
2. **`scm.py`** — maps a language name to its bundled tree-sitter tags query (`.scm`)
   file under `queries/`. Queries live in two collections (`tree-sitter-language-pack`,
   then `tree-sitter-languages`); the env var `PRIVREPOMAP_QUERIES` overrides the
   location. To support a new language you add its entry to `SCM_FILES` **and** ship the
   `.scm` file.
3. **`repomap.py` tag extraction** — `get_tags_raw()` parses each file with the pure
   `tree_sitter` `Parser` + `Query` API (NOT the language-pack's native parser, whose
   trees are incompatible with `tree_sitter.Query`) and emits `Tag(rel_fname, fname,
   line, name, kind)` where `kind` is `"def"` or `"ref"`. Parsers/queries are cached per
   language in `_PARSER_QUERY_CACHE`; per-file tags are cached on disk in
   `.repomap.tags.cache.v1/` (diskcache, keyed by mtime). On any `sqlite3` error the
   cache is wiped and rebuilt via `tags_cache_error()`.
4. **`repomap.py` ranking** — `get_ranked_tags()` builds a `networkx.MultiDiGraph`
   where an edge goes from a file that *references* an identifier to a file that
   *defines* it, then runs PageRank. `chat_files` seed the `personalization` vector;
   final per-tag scores are multiplied by boosts (`BOOST_CHAT`,
   `BOOST_MENTIONED_IDENT`, `BOOST_MENTIONED_FNAME`).
5. **`repomap.py` rendering + budgeting** — `to_tree()` renders ranked tags into source
   snippets via `grep_ast.TreeContext`. `get_ranked_tags_map_uncached()` **binary-searches
   the number of tags** to include so the rendered output fits `max_map_tokens`. Final
   output always passes through `redact()`.

`tokenizer.py` and `importance.py` are leaf helpers (token estimation; conventional
"important file" detection, currently computed for parity but not yet used to bias
ranking). `cli.py` and `server.py` are the two front-ends — both construct a `RepoMap`
and call `get_repo_map()`; keep them behaviorally aligned when changing the public flow.

## MCP tools

`server.py` exposes two FastMCP tools over stdio. `project_root` must be an absolute
path; other file arguments are relative to it.
- `repo_map(project_root, chat_files?, other_files?, token_limit=8192, …)` → `{"map", "report"}`
- `search_identifiers(project_root, query, max_results=50, context_lines=2, …)` → `{"results": [...]}`

Both offload the blocking `RepoMap` work to `asyncio.to_thread`. stdout is the MCP
protocol channel, so all logging goes to stderr at ERROR level — never `print()` to
stdout from server code paths.
