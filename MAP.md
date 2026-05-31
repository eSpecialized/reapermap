# Project Map

`privrepomap` is a private, offline, structural repository mapper. It builds token-budgeted code maps from tree-sitter definition/reference tags, ranks files with a PageRank graph, renders source context with `grep_ast`, and redacts likely secrets before output leaves the process.

## Entry points

- `privrepomap` -> `src/privrepomap/cli.py:main`
- `privrepomap-mcp` -> `src/privrepomap/server.py:main`
- Library exports -> `src/privrepomap/__init__.py`

Both front ends call the same `RepoMap` engine. The CLI prints maps to stdout and diagnostics to stderr. The MCP server exposes stdio tools and keeps stdout reserved for the protocol.

## Execution flow

```text
file discovery
  -> tag extraction
  -> defs/refs graph ranking
  -> tree rendering
  -> token budgeting
  -> redaction
  -> CLI or MCP output
```

1. `filescan.find_src_files` discovers candidate files while respecting `.gitignore` (root + nested, with early dir pruning), secret-file rules, size limits, binary detection, an expanded set of dependency/build/worktree/Xcode directory skips (case-insensitive), and the local tag cache directory.
2. `RepoMap.get_tags` reads fresh tags from the persistent cache or calls `RepoMap.get_tags_raw`.
3. `RepoMap.get_tags_raw` resolves a language, loads a bundled `.scm` tags query, parses with tree-sitter, and emits `Tag` records for definitions and references.
4. `RepoMap.get_ranked_tags` builds a NetworkX graph from references to definitions and ranks files with PageRank plus boosts for chat files, mentioned files, and mentioned identifiers.
5. `RepoMap.to_tree` renders selected lines of interest with `grep_ast.TreeContext`.
6. `RepoMap.get_ranked_tags_map_uncached` binary-searches the number of ranked tags that fit the token budget.
7. `RepoMap.get_repo_map` applies output redaction and returns the map plus a `FileReport`.

## Core data structures

- `RepoMap`: the central engine. It owns token budget settings, repository root, file/token helper callbacks, output handlers, in-memory map cache, tree-context cache, and persistent tag cache.
- `Tag`: `namedtuple("Tag", "rel_fname fname line name kind")`. `kind` is `"def"` or `"ref"`.
- `FileReport`: dataclass with `excluded`, `definition_matches`, `reference_matches`, and `total_files_considered` metadata.
- Persistent tag cache: `.repomap.tags.cache.v1/`, backed by `diskcache`, keyed by absolute file path and invalidated by mtime.
- Parser/query cache: module-level `_PARSER_QUERY_CACHE` in `repomap.py`, keyed by language name.
- File report metadata: returned by CLI/MCP flows to explain skipped files and tag counts without exposing file contents.

## Module inventory

### `src/privrepomap/__init__.py`

Package documentation and exports. Re-exports `RepoMap`, `Tag`, and `FileReport`, and defines `__version__`.

### `src/privrepomap/cli.py`

Command-line front end.

Important symbols:

- `build_parser`: defines CLI options, examples, and help text.
- `main`: expands file/directory inputs, constructs `RepoMap`, calls `get_repo_map`, prints map output, and returns process-style status codes.
- `_tool_output`, `_tool_warning`, `_tool_error`: route normal output to stdout and diagnostics to stderr.

Key options include `--root`, `--map-tokens`, `--chat-files`, `--other-files`, `--mentioned-files`, `--mentioned-idents`, `--token-strategy`, `--max-context-window`, `--force-refresh`, `--exclude-unranked`, and `--verbose`.

### `src/privrepomap/filescan.py`

Privacy-aware file discovery and reads.

Important symbols:

- `find_src_files`: returns absolute paths for scannable files from a file or directory input.
- `read_text`: central text read helper that refuses secret files and oversized files.
- `is_secret_file`: basename-based secret-file classifier.
- `_looks_binary`: NUL-byte binary sniffing helper.
- `_load_gitignore` / `_collect_gitignore_patterns`: loads root + all nested `.gitignore` files (with practical subdir prefixing for the spec), plus hardcoded cache/secret ignores. Early directory pruning uses the resulting spec.
- `SKIP_DIRS`, `SECRET_BASENAMES`, `SECRET_PREFIXES`, `SECRET_SUFFIXES`, `SECRET_ALLOWLIST`, `MAX_FILE_BYTES`: scanning policy constants.

This module is the choke point for avoiding secret-looking files, binary files, large files, dependency/build directories, and ignored paths.

### `src/privrepomap/importance.py`

Conventional important-file detection.

Important symbols:

- `is_important`: recognizes common docs, config, package, build, workflow, and license files.
- `filter_important_files`: filters relative paths down to important files.
- `IMPORTANT_FILENAMES`, `IMPORTANT_DIR_PATTERNS`: rule sets for the classifier.

The current engine computes important files for parity and future tuning; ranking is still driven primarily by the graph and explicit boosts.

### `src/privrepomap/redact.py`

Defense-in-depth secret redaction for rendered output.

Important symbols:

- `redact`: applies regex rules to mask likely secrets.
- `REDACTED`: replacement marker.
- `_RULES`: compiled regex patterns for AWS, GitHub, Slack, Google, Stripe/OpenAI-style keys, JWTs, authorization headers, generic key/secret/password/token assignments, and PEM private key bodies.

Redaction is heuristic. It reduces leakage risk but does not replace secret-file skipping or careful review before sharing generated maps.

### `src/privrepomap/repomap.py`

Core engine.

Important symbols:

- `RepoMap`: orchestrates tag extraction, graph ranking, rendering, budgeting, caching, and redaction.
- `Tag`: definition/reference record.
- `FileReport`: map metadata record.
- `_get_parser_and_query`: builds and caches a tree-sitter `Parser` plus `Query` for a language.
- `get_tags`: persistent cache wrapper for per-file tags.
- `get_tags_raw`: tree-sitter extraction from a single file.
- `get_ranked_tags`: PageRank ranking over the defs/refs graph.
- `render_tree`: source-context rendering with fallback line formatting.
- `to_tree`: groups ranked tags by file and renders map sections.
- `get_ranked_tags_map` and `get_ranked_tags_map_uncached`: in-memory map caching plus token-budget fitting.
- `get_repo_map`: public map-building API; applies final redaction.

Constants include cache version/name, SQLite error classes, ranking boosts, and personalization weights.

### `src/privrepomap/scm.py`

Tree-sitter tags query resolution.

Important symbols:

- `get_scm_fname`: returns a bundled tags query path for a language.
- `SCM_FILES`: language-to-query filename map.
- `_queries_root`: resolves the `queries/` root, including the `PRIVREPOMAP_QUERIES` override.
- `_COLLECTIONS`: search order for `tree-sitter-language-pack` and `tree-sitter-languages` query collections.

Query files are local project data. No query resolution path downloads content.

### `src/privrepomap/server.py`

FastMCP stdio server.

Important symbols:

- `repo_map`: MCP tool that mirrors the CLI map flow and returns `{ "map": str, "report": {...} }` or `{ "error": str }`.
- `search_identifiers`: MCP tool that now routes through `get_ranked_tags` (PageRank + boosts) so high-centrality definitions surface first. Returns matches with explicit `rank` values plus a `report` for symmetry with `repo_map`. Supports the same optional `chat_files` / `mentioned_*` context parameters.
- `main`: runs the stdio MCP server.
- `_token_counter`: heuristic token counter callback for server calls.

Telemetry-related environment defaults are set before importing FastMCP. Logging goes to stderr only.

### `src/privrepomap/tokenizer.py`

Offline token estimation.

Important symbols:

- `count_tokens`: strategy selector.
- `estimate_tokens_heuristic`: fast `len(text) / 4.0` estimate.
- `estimate_tokens_pygments`: local Pygments lexer token estimate with heuristic fallback.
- `CHARS_PER_TOKEN`: stable heuristic constant.

`tiktoken` is intentionally not used because it can download vocabularies on first use.

## Cross-module relationships

```text
cli.py ─┬─ filescan.find_src_files/read_text
        ├─ tokenizer.count_tokens
        └─ repomap.RepoMap

server.py ─┬─ filescan.find_src_files/read_text
           ├─ tokenizer.count_tokens
           ├─ redact.redact
           └─ repomap.RepoMap

repomap.py ─┬─ filescan.read_text
            ├─ importance.filter_important_files
            ├─ redact.redact
            ├─ scm.get_scm_fname
            └─ tokenizer.count_tokens
```

## Tests map

- `tests/conftest.py`: creates a tiny multi-file fixture repository with Python definitions/references, `.gitignore`, ignored files, secret files, and an allowed source file containing fake secrets.
- `tests/test_filescan.py`: validates secret basename detection, `.gitignore` behavior, secret-file skipping, and direct read refusal for secrets.
- `tests/test_offline.py`: blocks socket creation/connections and verifies tokenizer and map generation do not touch the network.
- `tests/test_redact.py`: covers AWS key, generic API key, JWT, PEM body, and plain-text redaction behavior.
- `tests/test_repomap.py`: covers end-to-end map generation, token budgeting, output redaction, and identifier tag extraction.
- `tests/test_tokenizer.py`: covers empty input, heuristic scaling, Pygments token counting, and strategy selection.

## Documentation style

- Keep markdown concise and practical.
- Prefer bullet lists and fenced examples for commands or flow diagrams.
- Keep Python docstrings short but architectural: role, public symbols, privacy/security notes where relevant.
- Avoid documenting behavior that is not implemented yet.
