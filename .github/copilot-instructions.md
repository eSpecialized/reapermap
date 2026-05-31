# Copilot instructions for privrepomap

## Build, test, and run

- Install for development: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[test]"`
- Run the full test suite: `pytest -q`
- Run one test file: `pytest -q tests/test_repomap.py`
- Run one test: `pytest -q tests/test_repomap.py::test_map_generation`
- Run the CLI locally after editable install: `privrepomap .` or `python -m privrepomap.cli .`
- Run the MCP server over stdio after editable install: `privrepomap-mcp`

No lint/type-check command is configured in this repository.

## Architecture

- The package lives under `src/privrepomap` and is distributed as the `privrepomap` Python package. `pyproject.toml` defines two console scripts: `privrepomap` (`privrepomap.cli:main`) and `privrepomap-mcp` (`privrepomap.server:main`).
- `RepoMap` in `src/privrepomap/repomap.py` is the core engine. It extracts tree-sitter definition/reference tags, builds a defs-to-refs graph, ranks files with NetworkX PageRank, renders lines of interest with `grep_ast.TreeContext`, fits output to a token budget, and redacts secrets before returning map text.
- `src/privrepomap/filescan.py` centralizes repository scanning and file reads. It respects `.gitignore`, skips secret-looking files, binary files, oversized files, dependency/build directories, and the local `.repomap.tags.cache.v*/` cache.
- `src/privrepomap/scm.py` maps language names to bundled tree-sitter query files under `queries/`, preferring `queries/tree-sitter-language-pack` over `queries/tree-sitter-languages`. `PRIVREPOMAP_QUERIES` can override query lookup.
- `src/privrepomap/tokenizer.py` intentionally avoids `tiktoken`; token budgeting uses deterministic offline estimates (`heuristic` by default, `pygments` optionally).
- `src/privrepomap/server.py` wraps the same engine as FastMCP tools: `repo_map` and `search_identifiers`. It sets telemetry-disabling environment defaults before importing FastMCP and keeps stdout reserved for MCP transport.
- Tests in `tests/` use a generated fixture repository from `tests/conftest.py`; `tests/test_offline.py` monkeypatches `socket` to fail on any network access.

## Repository-specific conventions

- Preserve the offline/privacy guarantees. Do not add dependencies or code paths that make network calls, download token vocabularies, emit telemetry, or bypass redaction.
- Route all repository content reads through `read_text`/`find_src_files` unless there is a deliberate reason to bypass size, binary, `.gitignore`, and secret-file guards.
- All externally returned map/search output should pass through `redact` as defense in depth, even when files were already screened.
- Keep stdout clean in MCP server code; use stderr logging for errors so the stdio MCP channel is not polluted.
- When changing ranking behavior, account for all existing boosts: chat files, mentioned filenames, mentioned identifiers, `exclude_unranked`, and the `max_context_window` budget expansion path.
- The persistent tag cache is local and gitignored at `.repomap.tags.cache.v*/`; use `force_refresh` to bypass map cache behavior in CLI/MCP flows when needed.
