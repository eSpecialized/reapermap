# Security Notes

This is a practical security audit for `privrepomap`, not a vulnerability disclosure policy. It describes the current trust model, implemented mitigations, known limitations, and safe-use guidance.

## Executive summary

Overall risk is **medium** for untrusted or multi-tenant usage and **lower** for trusted local repositories.

The project is designed for local, offline source analysis. Its strongest controls are no network access, telemetry opt-out defaults, privacy-aware file scanning, size/binary filters, and output redaction. The main residual risks are local filesystem exposure, heuristic redaction limits, lack of sandboxing/authentication around MCP callers, and denial-of-service potential on large or adversarial repositories.

## Threat model

In scope:

- Local filesystem access to repositories provided by the user or MCP caller.
- Repository contents, including source files that may contain embedded credentials.
- MCP tool callers that can supply paths, token limits, search strings, and file lists.
- Output leakage through generated maps, identifier search context, reports, logs, or error strings.
- Dependency and parser behavior for tree-sitter, Pygments, NetworkX, diskcache, pathspec, grep-ast, and FastMCP.

Out of scope today:

- Authentication and authorization for MCP callers.
- Sandboxing, containerization, seccomp, filesystem jails, or allowed-root enforcement.
- Multi-tenant isolation.
- Formal secrets detection guarantees.
- Hard operation timeouts for parsing, ranking, Pygments tokenization, or async server work.

Authentication, authorization, isolation, and process sandboxing are caller/environment responsibilities today.

## Existing mitigations

- **Offline by design:** no embeddings, no cloud search, no tokenizer downloads, and no intentional network paths.
- **No `tiktoken`:** token counts use local heuristic or Pygments estimates.
- **Telemetry disabled before FastMCP import:** `FASTMCP_DISABLE_TELEMETRY`, `DO_NOT_TRACK`, and `ANONYMIZED_TELEMETRY` are set before `fastmcp` is imported.
- **`.gitignore` support:** repository scans respect root `.gitignore` through `pathspec`.
- **Secret-file skipping:** `.env`, `*.pem`, `*.key`, `id_rsa*`, `credentials*`, `.npmrc`, `.pypirc`, and related names are skipped.
- **Sample env allowlist:** `.env.example`, `.env.sample`, and `.env.template` are allowed because they are commonly useful documentation/config samples.
- **Size cap:** files over 1 MB are skipped by scanner/read helpers.
- **Binary detection:** files with NUL bytes in the initial sniff are skipped.
- **Local cache:** tags are cached in `.repomap.tags.cache.v1/`, which is also excluded from scans.
- **Output redaction:** all returned map output passes through `redact`; identifier search contexts are redacted too.
- **Tests:** offline behavior, redaction, scanner filtering, token budgeting, and map generation are covered in `tests/`.

## Known limitations

- **Heuristic redaction:** regex rules can miss unusual secret formats and can redact false positives.
- **Path disclosure:** errors and reports may include local absolute paths.
- **Path containment:** symlink and path containment are not explicitly enforced as a security boundary.
- **Trusted MCP inputs:** MCP tool inputs are treated as trusted local requests.
- **No auth/z:** the stdio MCP server does not authenticate or authorize callers.
- **No hard timeouts:** large or adversarial files/repos can spend CPU in parsing, graph ranking, Pygments tokenization, or rendering.
- **Weak input bounds:** `token_limit`, `max_results`, and `context_lines` are normalized in some cases but not enforced as strict security limits.
- **Parser/query trust:** bundled query files and `PRIVREPOMAP_QUERIES` are treated as trusted local configuration.

## Module-by-module notes

### `src/privrepomap/filescan.py`

Severity: **medium** for untrusted repos, **low** for trusted local repos.

Strengths:

- Centralizes file discovery and text reads.
- Skips secret-looking basenames and extensions.
- Applies `.gitignore` rules during scans.
- Skips dependency/build/cache directories.
- Enforces a 1 MB file cap.
- Performs simple binary sniffing.

Caveats:

- Path containment is not an explicit security boundary.
- Symlinks and unusual filesystem layouts can expose paths outside the intended project if the caller gives such paths.
- Direct single-file inputs are filtered for secret basenames but are not checked for binary/size until read time by downstream code.
- Error output from `read_text(..., silent=False)` may reveal local paths.

### `src/privrepomap/redact.py`

Severity: **medium** because it is a defense-in-depth control, not a guarantee.

Strengths:

- Covers AWS access keys and assigned AWS secret keys.
- Covers GitHub, Slack, Google API, Stripe, OpenAI-style keys, JWTs, bearer/authorization headers, generic secret/password/token assignments, and PEM private key bodies.
- Runs on all returned repository maps and identifier contexts.

Caveats:

- Redaction is regex-based and heuristic.
- Unknown token shapes can pass through.
- False positives are possible.
- Regex performance should be monitored if rules become more complex or inputs become very large.

### `src/privrepomap/server.py`

Severity: **medium** for local single-user use, **high** if exposed to untrusted callers.

Strengths:

- Uses stdio transport rather than opening a listening network socket.
- Sets telemetry opt-out environment variables before importing FastMCP.
- Logs to stderr so stdout remains the MCP protocol channel.
- Redacts identifier search context.

Caveats:

- Assumes callers are trusted.
- Does not implement authentication, authorization, allowed roots, or sandboxing.
- Does not enforce hard operation timeouts.
- Allows caller-controlled paths and file lists.
- `max_results`, `context_lines`, and token budgets are not strict resource controls.
- Error responses may disclose local paths or exception details.

### `src/privrepomap/repomap.py`

Severity: **medium** for untrusted large repos, **low** for trusted repos.

Strengths:

- Applies final redaction in `get_repo_map`.
- Uses centralized `read_text` by default.
- Caches tags by mtime and handles SQLite cache errors by rebuilding/falling back.
- Catches parser failures per file and continues.
- Handles `RecursionError` by disabling map generation for that call path.

Caveats:

- `get_rel_fname` falls back to absolute paths for files outside root, which can leak paths in output or reports.
- Large repo graphs can be expensive for PageRank.
- Parsing and rendering do not have hard per-file or per-operation timeouts.
- Cache contents are local but not encrypted.

### `src/privrepomap/tokenizer.py`

Severity: **low**.

Strengths:

- Avoids `tiktoken` and tokenizer vocabulary downloads.
- Heuristic strategy is fast, deterministic, and offline.
- Pygments strategy is local and falls back to the heuristic.

Caveats:

- Pygments can be slower on pathological inputs.
- Token counts are estimates, not exact model tokenization.

### `src/privrepomap/scm.py` and `queries/`

Severity: **low** with trusted project files, **medium** if `PRIVREPOMAP_QUERIES` is untrusted.

Strengths:

- Resolves local bundled query files only.
- Does not download grammar or query data.
- Searches known local query collections in a stable order.

Caveats:

- `PRIVREPOMAP_QUERIES` should be treated as trusted configuration.
- Malformed or adversarial query files can cause parser/query errors or CPU cost.

### `src/privrepomap/cli.py`

Severity: **low** for trusted local use.

Strengths:

- Uses the same scanner, reader, token counter, and redaction path as the engine.
- Sends diagnostics to stderr and map output to stdout.

Caveats:

- CLI callers can point the tool at arbitrary local paths available to the process.
- Verbose errors can include exception details and local paths.

### `src/privrepomap/importance.py`

Severity: **low**.

This module only classifies filenames and relative paths as conventionally important. It does not read files or expose content.

## Dependency notes

- `fastmcp`: MCP server framework. Telemetry env defaults are set before import; stdio should still be treated as a trusted local channel.
- `pygments`: optional local token-estimation strategy; can be CPU-heavy on unusual input.
- `tree-sitter` and `tree-sitter-language-pack`: parsing layer; query/parser failures are caught per file where possible.
- `diskcache`: persistent local tag cache backed by SQLite; cache data is local and not encrypted.
- `networkx`: PageRank implementation; large graphs can consume CPU/memory.
- `pathspec`: `.gitignore` handling for scans.
- `grep-ast`: tree-context rendering for selected source lines.
- `tiktoken`: intentionally not used because it may download vocabularies.

## User guidance

- Run against trusted repositories when possible.
- Isolate the MCP server process when analyzing untrusted code.
- Do not expose stdio MCP access to untrusted callers.
- Review generated maps and search results before sharing them outside your environment.
- Keep dependencies updated and monitor parser/MCP/security advisories.
- Treat `PRIVREPOMAP_QUERIES` as trusted local configuration.

## Hardening ideas

Possible follow-up implementation work:

- Enforce allowed project roots and path containment.
- Normalize and clamp `token_limit`, `max_results`, and `context_lines` as resource controls.
- Add per-operation timeouts for MCP calls.
- Add symlink policy tests.
- Add redaction performance tests.
- Reduce path detail in user-facing error responses.
- Add optional cache cleanup guidance or cache location configuration.
