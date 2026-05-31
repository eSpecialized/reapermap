# Plan: Private, Offline RepoMapper Rebuild

A clean-room Python rebuild of `pdavis68/RepoMapper` as a private, hardened tool you fully control. It keeps the **structural** approach (tree-sitter parsing + PageRank ranking + token-budgeted output) — which is already language-agnostic and context-small — and adds strict privacy guarantees so it can serve as your offline replacement for Copilot's `semantic_search`. Ships as both an MCP server and a CLI.

**Key finding:** The original is *already* offline and structural — but it uses `tiktoken` for token counting, which downloads its vocab from OpenAI on first use. That's the one real network dependency, and the rebuild replaces it with an offline token estimator.

## Decisions

- Search style: **Structural only** (tree-sitter + PageRank map + identifier search). No embeddings.
- Language: **Python** (clean-room fork of the design, not copied code).
- Integration: **MCP server (FastMCP) + CLI**.
- Privacy (all required): strictly offline, no telemetry, respect `.gitignore` + skip secrets/`.env`, redact secrets from output, cache local & gitignored.
- Hosting: **new local folder + new private GitHub repo**.
- Excludes: embeddings/NL semantic search, telemetry, cloud sync.

## Steps

### Phase 1 — Scaffold private repo
1. New local folder, `git init`, `pyproject.toml` with offline-only deps (`networkx`, `diskcache`, `grep-ast`, `tree-sitter`, `tree-sitter-language-pack`, `pygments`, `fastmcp`) — **no tiktoken**. `.gitignore` excludes cache dir, venv, `.env`.
2. Copy the `queries/*.scm` tree-sitter grammar files (MIT data) + add `LICENSE`/`NOTICE` attributing Aider/RepoMapper design.

### Phase 2 — Core engine (clean-room) *(depends on Phase 1)*
3. `tokenizer.py` — offline token estimate (heuristic ~chars/4 or pygments lexer token counts), no network.
4. `filescan.py` — repo walk that respects `.gitignore` (via `pathspec`) and skips secrets (`.env`, `*.pem`, `id_rsa`, `*.key`, `credentials*`, `.aws`), binaries, large files, and build/VCS dirs.
5. `scm.py` + `importance.py` — language→query mapping and important-file ranking.
6. `repomap.py` core — Tag extraction, defs/refs graph, PageRank, token-budget binary search, `TreeContext` rendering, with `chat_files > mentioned_files > others` boosting.
7. `redact.py` — regex redaction of secrets/tokens (AWS keys, bearer/JWT, API keys, private keys, high-entropy) applied to **all** rendered output before return.

### Phase 3 — Interfaces *(depends on Phase 2)*
8. `cli.py` — argparse mirroring original flags (`project_root`, `--chat-files`, `--mentioned-files`, `--mentioned-idents`, `--map-tokens`, `--force-refresh`, `--exclude-unranked`, `--verbose`).
9. `server.py` — FastMCP server exposing `repo_map()` + `search_identifiers()`, telemetry disabled, stateless stdio, output run through redaction.

### Phase 4 — Privacy hardening + verification
10. Offline guard test that monkeypatches `socket` to **prove** zero network calls.
11. Tests: offline tokenizer, gitignore respected, secret files skipped, redaction works, map generation on a fixture repo, identifier search, network-block test.
12. `README` with privacy guarantees + VS Code `mcp.json` config snippet.

### Phase 5 — Publish *(needs confirmation)*
13. Create private GitHub repo (`gh repo create --private`) and push. Confirm first.
14. Point VS Code MCP config at the new server; verify `repo_map` runs against `bCandied2019`.

## Proposed layout

```
private-repomap/
  pyproject.toml
  .gitignore
  LICENSE
  NOTICE
  README.md
  src/privrepomap/
    tokenizer.py
    filescan.py
    scm.py
    importance.py
    repomap.py        # core engine
    redact.py
    cli.py
    server.py
  queries/            # copied .scm tree-sitter grammars (35+ langs)
  tests/
```

## Reference (original at `<repoRoot>/source2025/github/RepoMapper`)

- `repomap.py` — CLI entry
- `repomap_class.py` — core RepoMap: tags cache (diskcache), tree-sitter parse via grep-ast, PageRank (networkx), token-budget binary search, `render_tree` (grep_ast `TreeContext`)
- `repomap_server.py` — FastMCP server: tools `repo_map()` + `search_identifiers()`
- `importance.py` — `IMPORTANT_FILENAMES`, `is_important`, `filter_important_files`
- `scm.py` — `get_scm_fname(lang)` → `queries/<pack>/<lang>-tags.scm`
- `utils.py` — `count_tokens` (the tiktoken risk), `read_text`, `Tag` namedtuple
- `queries/` — `.scm` tree-sitter query files (35+ langs)

## Verification

1. Run network-block test suite — must pass with sockets disabled.
2. Run CLI against `bCandied2019` and confirm a token-bounded map is produced.
3. Confirm `.env`/secret fixtures are excluded and a planted fake API key is redacted in output.
4. Launch MCP server, call `repo_map` from VS Code, confirm parity with current tool.

## Open items to confirm

1. **Tool/repo name + local path?** Recommend `private-repomap` at `~/source2025/github/private-repomap`.
2. **Repo creation:** use `gh repo create --private`, or create it manually?
3. **Coexistence:** replace the current `/usr/local/bin/repomap` + MCP entry, or run side-by-side under a new name first? Recommend **side-by-side** until verified.

# Post Implementation by Opus 4.8 Agent

Ran terminal command:  source .venv/bin/activate && python -m pytest -q -W ignore::DeprecationWarning 2>&1 | tail -25

All 19 tests pass. Let me verify the CLI and MCP server work end-to-end against a real codebase.    

Ran terminal command:  source .venv/bin/activate && echo "=== CLI on own src ===" && privrepomap src/ --map-tokens 800 --verbose 2>&1 | head -30 && echo "..." && echo "=== server imports ===" && python -c "from privrepomap import server; print('server OK, tools registered')"

Starting: *Create README and verify implementation* (5/5)

Everything works end-to-end. Let me check for any static errors and update my progress notes.     

Checked [](file://<repoRoot>/source2025/reapermap/src/privrepomap/repomap.py), [](file://<repoRoot>/source2025/reapermap/src/privrepomap/cli.py), [](file://<repoRoot>/source2025/reapermap/src/privrepomap/server.py), [](file://<repoRoot>/source2025/reapermap/src/privrepomap/filescan.py), no problems found

Updated memory file [](file://<repoRoot>/Library/Application%20Support/Code%20-%20Insiders/User/workspaceStorage/eaa2e7427b336f0e7318f8d8e9b4335e/GitHub.copilot-chat/memory-tool/memories/YTAxNjljNjgtOGQyYS00NzBlLTlhNWUtYWU2MWJjNDQxMDE3/repomap-rebuild.md)

Phases 1–4 are complete and verified. Here's what was built in the workspace:

**Structure created**
- pyproject.toml — offline-only deps (`networkx`, `diskcache`, `grep-ast`, `tree-sitter`, `tree-sitter-language-pack`, `pygments`, `fastmcp`, `pathspec`); **no `tiktoken`**
- .gitignore, NOTICE, README.md (LICENSE already existed)
- queries/ — copied 49 `.scm` grammar files
- privrepomap: tokenizer.py, filescan.py, scm.py, importance.py, repomap.py, redact.py, cli.py, server.py
- tests: tokenizer, filescan/gitignore, redaction, end-to-end map, and a socket-blocking offline test

**Key outcomes**
- Offline token estimator replaces tiktoken (heuristic + pygments strategies).
- .gitignore-aware scanning, secret-file skipping, and regex redaction applied to all output.
- **19/19 tests pass**, including the network-block proof.
- CLI verified: produced a token-bounded map (662 tokens under an 800 budget) of its own source; MCP server imports cleanly.

**One notable fix:** the installed `tree-sitter-language-pack` returns a native Rust parser incompatible with `tree_sitter.Query`, so the engine now builds its own `tree_sitter.Parser` + `Query` from the `Language` object. (Also requires Python 3.13, which I used for the venv.)

**Phase 5 needs your confirmation before I proceed.** A few questions:

1. **Create the private GitHub repo now?** I'd run `gh repo create --private` and push this workspace. Confirm before I do anything that touches GitHub.
2. **Repo name** — keep it as `reapermap` (current folder), or rename to `private-repomap`?
3. **VS Code MCP wiring** — want me to add an `mcp.json` entry pointing at privrepomap-mcp side-by-side with your current tool (recommended), or replace the existing one?

Completed: *Create README and verify implementation* (5/5)

Made changes.