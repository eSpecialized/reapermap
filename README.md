# privrepomap

A **private, offline, structural** repository mapper. It produces a
token-budgeted map of a codebase — function/class signatures and the most
relevant files — using tree-sitter parsing and PageRank ranking. It ships as
a **CLI** and an **MCP server**, and is designed as an offline replacement for
cloud `semantic_search`.

This is a clean-room reimplementation inspired by the design of
[RepoMapper](https://github.com/pdavis68/RepoMapper) and
[Aider](https://github.com/Aider-AI/aider)'s repo map. See [NOTICE](NOTICE).

## Dependencies

tree sitter language pack from
    https://github.com/kreuzberg-dev/tree-sitter-language-pack

## Privacy guarantees

- **Strictly offline.** No network calls. Token counting is done with a local
  estimator (`tiktoken` is intentionally *not* a dependency). A test suite
  monkeypatches `socket` to prove zero network access.
- **No telemetry, no cloud sync, no embeddings.** Structural search only.
- **`.gitignore`-aware.** Scanning respects `.gitignore` via `pathspec`.
- **Secret files skipped.** `.env`, `*.pem`, `*.key`, `id_rsa*`,
  `credentials*`, etc. are never read or indexed (`.env.example` is allowed).
- **Output redaction.** All rendered output is passed through regex redaction
  for AWS/GitHub/Slack/Google/Stripe/OpenAI keys, JWTs, bearer tokens, PEM
  private keys, and generic `key=secret` assignments.
- **Local, gitignored cache.** Tag cache lives in
  `.repomap.tags.cache.v1/` and is gitignored.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## CLI usage

```bash
# Map the current directory (8192-token budget by default)
privrepomap .

# Map src/ with a smaller budget
privrepomap src/ --map-tokens 2048

# Boost the file you're working on, map the rest as context
privrepomap . --chat-files src/app/main.py --mentioned-idents handleClick

# Use the slightly more accurate (but slower) offline token estimator
privrepomap . --token-strategy pygments
```

Key flags: `--root`, `--map-tokens`, `--chat-files`, `--other-files`,
`--mentioned-files`, `--mentioned-idents`, `--exclude-unranked`,
`--force-refresh`, `--verbose`.

## MCP server

Run over stdio:

```bash
privrepomap-mcp
```

VS Code `mcp.json` snippet:

```json
{
  "servers": {
    "privrepomap": {
      "type": "stdio",
      "command": "/absolute/path/to/.venv/bin/privrepomap-mcp",
      "env": {
        "DO_NOT_TRACK": "1",
        "FASTMCP_DISABLE_TELEMETRY": "1"
      }
    }
  }
}
```

Tools exposed:

- `repo_map(project_root, chat_files?, other_files?, token_limit?, …)` —
  returns `{ "map": str, "report": {...} }`.
- `search_identifiers(project_root, query, …)` — returns `{ "results": [...] }`.

## Tests

```bash
pip install -e ".[test]"
pytest -q
```

The `tests/test_offline.py` suite blocks `socket` to verify the engine makes
no network calls.

## Linting

```bash
pip install -e ".[lint]"
ruff check src tests
```

## Project docs

- [MAP.md](MAP.md) — source map, module inventory, execution flow, and tests map.
- [SECURITY.md](SECURITY.md) — practical security notes, mitigations, limitations, and safe-use guidance.

## License

MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
