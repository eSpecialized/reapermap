## Plan: Project Documentation Map

Create practical project documentation for the Python source in `src/privrepomap/`: add top-level `MAP.md`, add top-level `SECURITY.md`, and improve module/function docstrings where they help explain the larger architecture. The recommended approach is documentation-first and behavior-preserving: no runtime logic changes, no security hardening implementation in this pass, and no README update unless the executor chooses to add a minimal link/navigation note.

**Steps**
1. Review current documentation tone and source docstring style.
   - Read `README.md`, `INSTRUCTIONS.md`, `pyproject.toml`, and all files under `src/privrepomap/*.py`.
   - Preserve the existing markdown style: concise headings, bullet lists, fenced command examples where needed, privacy/offline framing.
   - Preserve Python style: short module docstrings plus targeted function/class docstrings; do not add noisy comments.

2. Draft `MAP.md` as the project-wide source map.
   - Include a short project overview: `privrepomap` is an offline, privacy-first repository mapper that builds token-budgeted code maps from tree-sitter tags and PageRank ranking.
   - Include entry points: CLI console script `privrepomap` via `src/privrepomap/cli.py:main`, and MCP server `privrepomap-mcp` via `src/privrepomap/server.py:main`.
   - Include the main execution flow: file discovery -> tag extraction -> graph ranking -> tree rendering -> token budgeting -> redaction -> CLI/MCP output.
   - Include module-by-module sections for every Python source file with important symbols and responsibilities.
   - Include data structures and cross-module relationships: `RepoMap`, `Tag`, `FileReport`, persistent cache, parser/query cache, file report metadata.
   - Include tests map: explain what each `tests/test_*.py` validates.

3. Fill `MAP.md` module inventory.
   - `src/privrepomap/__init__.py` — package exports: `RepoMap`, `Tag`, `FileReport`, `__version__`.
   - `src/privrepomap/cli.py` — `build_parser`, `main`; parses CLI options, scans inputs, calls `RepoMap.get_repo_map`, prints map and metadata.
   - `src/privrepomap/filescan.py` — `find_src_files`, `read_text`, `is_secret_file`, `_looks_binary`, `_load_gitignore`; handles privacy-aware scanning, size limits, binary detection, `.gitignore`, secret-file skipping.
   - `src/privrepomap/importance.py` — `is_important`, `filter_important_files`; recognizes conventional project files and docs/config paths.
   - `src/privrepomap/redact.py` — `redact`, `REDACTED`; masks common credential/token patterns in rendered output.
   - `src/privrepomap/repomap.py` — `RepoMap`, `Tag`, `FileReport`, `_get_parser_and_query`; central engine for tag extraction, PageRank ranking, token budgeting, rendering, caching, and redaction.
   - `src/privrepomap/scm.py` — `get_scm_fname`, `SCM_FILES`, `_queries_root`; resolves bundled tree-sitter tags query files, including `PRIVREPOMAP_QUERIES` override.
   - `src/privrepomap/server.py` — FastMCP tools `repo_map` and `search_identifiers`, `main`; exposes repo mapping and identifier search over stdio.
   - `src/privrepomap/tokenizer.py` — `count_tokens`, `estimate_tokens_heuristic`, `estimate_tokens_pygments`; local token estimation with heuristic default and Pygments fallback strategy.

4. Draft `SECURITY.md` as a practical security audit.
   - Include an executive summary: overall risk is medium for untrusted/multi-tenant usage, lower for trusted local repos.
   - Include threat model: local filesystem access, repo contents, MCP callers, output leakage, dependency/parser behavior; explicitly state that auth/z and sandboxing are caller/environment responsibilities today.
   - Include existing mitigations: no network/tokenizer downloads, telemetry disable in MCP setup, `.gitignore` support, secret-file skip list, allowlisted sample env files, 1MB file cap, binary detection, defense-in-depth output redaction, tests for offline behavior and redaction.
   - Include limitations: redaction is heuristic, path errors may reveal local paths, symlink/path containment is not explicitly enforced, MCP inputs are trusted, async work and Pygments/tree parsing have no hard timeout.
   - Include module-by-module security notes and severity labels, using wording that is accurate but not alarmist.
   - Include practical user guidance: run against trusted repos, isolate MCP server when analyzing untrusted code, review generated maps before sharing, monitor dependencies.

5. Fill `SECURITY.md` findings.
   - `filescan.py`: secret skipping and size/binary filtering are strengths; document symlink/path-containment and path-disclosure caveats.
   - `redact.py`: redaction covers AWS, GitHub, Slack, Google, Stripe/OpenAI-style keys, JWTs, authorization headers, generic secrets, and PEM bodies; document heuristic limits and possible regex performance concerns.
   - `server.py`: stdio MCP reduces network exposure and telemetry is disabled; document trusted-caller assumption, lack of authentication/authorization, unbounded or weakly bounded inputs such as `max_results` and token limits, no operation timeout, and path disclosure in errors.
   - `repomap.py`: output redaction and cache invalidation are strengths; document path fallback to absolute paths, PageRank/large-repo DoS potential, and `RecursionError` behavior.
   - `tokenizer.py`: heuristic strategy is fast/offline; Pygments strategy may be slower on pathological input.
   - `scm.py` and query files: bundled offline query resolution is a privacy strength; `PRIVREPOMAP_QUERIES` should be treated as trusted configuration.
   - Dependencies: call out `fastmcp`, `pygments`, `tree-sitter`, `diskcache`, `networkx`, `pathspec`, and note that `tiktoken` is intentionally not used.

6. Add focused Python docstring improvements.
   - Keep changes minimal and explanatory, not duplicating `MAP.md`.
   - Add or expand module docstrings where source files only have terse descriptions so each module states: role in the pipeline, main public symbols, and privacy/security behavior when relevant.
   - Add or expand docstrings for important public APIs if current docs are too sparse: `RepoMap`, `RepoMap.get_repo_map`, `RepoMap.get_ranked_tags`, `RepoMap.get_tags_raw`, `find_src_files`, `read_text`, `redact`, `get_scm_fname`, MCP tool functions, and tokenizer functions.
   - Avoid inline comments unless a short note clarifies a non-obvious security/privacy design choice.
   - Do not alter function signatures, behavior, cache formats, imports, or tests except if a docstring-only lint issue requires formatting.

7. Optional navigation polish, only if it fits existing docs.
   - Consider adding a short link section in `README.md` pointing to `MAP.md` and `SECURITY.md`.
   - Keep this optional because the selected scope was markdown docs plus docstrings, not a README rewrite.

8. Verification.
   - Run `pytest` to ensure docstring edits did not change behavior.
   - Run a documentation spell/format sanity pass manually by opening `MAP.md` and `SECURITY.md` and checking for broken headings, stale file names, and overclaiming.
   - Run `python -m privrepomap.cli --help` or the console equivalent if the environment supports the package, only to verify CLI names/options referenced in docs.
   - If import paths are not installed, use the repo’s preferred editable setup from `pyproject.toml` or run tests through the existing test command instead.

**Relevant files**
- `/Users/wthomps/source2025/reapermap/MAP.md` — new project map documentation.
- `/Users/wthomps/source2025/reapermap/SECURITY.md` — new practical security audit documentation.
- `/Users/wthomps/source2025/reapermap/README.md` — optional link-only update if useful.
- `/Users/wthomps/source2025/reapermap/src/privrepomap/__init__.py` — package exports documentation context.
- `/Users/wthomps/source2025/reapermap/src/privrepomap/cli.py` — CLI parser and main flow docstrings.
- `/Users/wthomps/source2025/reapermap/src/privrepomap/filescan.py` — scanning/privacy docstrings.
- `/Users/wthomps/source2025/reapermap/src/privrepomap/importance.py` — important-file helper docs.
- `/Users/wthomps/source2025/reapermap/src/privrepomap/redact.py` — redaction limitations and coverage docs.
- `/Users/wthomps/source2025/reapermap/src/privrepomap/repomap.py` — central architecture and public API docs.
- `/Users/wthomps/source2025/reapermap/src/privrepomap/scm.py` — query resolution docs.
- `/Users/wthomps/source2025/reapermap/src/privrepomap/server.py` — MCP tool and trust-boundary docs.
- `/Users/wthomps/source2025/reapermap/src/privrepomap/tokenizer.py` — offline token estimation docs.
- `/Users/wthomps/source2025/reapermap/tests/test_filescan.py` — referenced by docs as privacy scanning coverage.
- `/Users/wthomps/source2025/reapermap/tests/test_offline.py` — referenced by docs as no-network coverage.
- `/Users/wthomps/source2025/reapermap/tests/test_redact.py` — referenced by docs as redaction coverage.
- `/Users/wthomps/source2025/reapermap/tests/test_repomap.py` — referenced by docs as end-to-end map/redaction coverage.
- `/Users/wthomps/source2025/reapermap/tests/test_tokenizer.py` — referenced by docs as tokenizer coverage.

**Verification**
1. Run `pytest` from `/Users/wthomps/source2025/reapermap`.
2. Run CLI help through the installed console script or module form available in the environment to confirm documented option names.
3. Manually review `MAP.md` for a complete file/function inventory of `src/privrepomap/*.py`.
4. Manually review `SECURITY.md` for balanced language: current mitigations, known limitations, and user recommendations are all present.
5. Confirm no runtime code changes beyond docstrings/comments and no dependency changes.

**Decisions**
- User selected markdown plus docstrings.
- User selected a practical security audit, not a formal security policy.
- This plan documents risks but does not implement hardening fixes.
- Do not create a separate docs directory unless the executor strongly prefers it; the user explicitly requested top-level `MAP.md` and `SECURITY.md`.

**Further Considerations**
1. Security hardening can be a follow-up implementation plan: allowed roots for MCP, explicit min/max bounds, operation timeouts, safer path containment, and redaction performance tests.
2. If the docs become large, a future split into `docs/architecture.md` and `docs/security-audit.md` could keep top-level files shorter, but the requested deliverables should remain top-level.
