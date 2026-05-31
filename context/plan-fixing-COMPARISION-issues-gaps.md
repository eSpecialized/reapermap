# Plan: reapermap improvements from COMPARISON-reapermap-vs-RepoMapper.md

## Problem

The comparison doc (`COMPARISON-reapermap-vs-RepoMapper.md`) scores reapermap 118/160
(~74%) and identifies concrete headroom. The single largest gap is that the bundled
Swift tags query extracts **definitions only** (3575 defs / 0 refs on a real Xcode
project), so the PageRank graph has no edges and ranking collapses to flat. Several
follow-on relevance issues compound this (test files dominate `search_identifiers`,
canonical definitions don't surface first, no caller control over noise, no visibility
into why ranking is flat).

Separately, a latent ranking defect was found in `get_ranked_tags` (repomap.py:372-378):
PageRank only runs when `personalization` (chat files) is non-empty; otherwise every
node is assigned a flat rank of `1.0`. This means even with a valid reference graph,
default CLI/MCP runs (no chat files) get no centrality ranking.

## Approach

Implement all 5 recommendations from the doc plus the flat-rank fix, in priority order.
Preserve the hard privacy/offline invariants throughout (no network, no tiktoken, no
telemetry; route reads through `read_text`/`find_src_files`; all output through
`redact`). Keep `cli.py` and `server.py` behaviorally aligned. Add/extend tests for
each change and keep the offline test suite green.

## Todos

1. **swift-refs (P0): Extend `swift-tags.scm` with reference captures**
   - File: `queries/tree-sitter-language-pack/swift-tags.scm`
   - Add `@name.reference.*` captures for: call sites (`call_expression` →
     `simple_identifier`/member access), type references in signatures, variable/param
     type annotations (`type_identifier`), protocol conformance / inheritance
     (`inheritance_specifier`), extension targets (`(class_declaration) extension`
     name), and constructor/type usage.
   - Validate against the tree-sitter-swift grammar node names actually present (parse
     a sample Swift file via the pure `tree_sitter` Parser+Query API, as repomap.py
     does — NOT the language-pack native parser).
   - Add a fixture Swift file under `tests/` (or extend conftest fixture repo) with
     known defs + refs and assert non-zero reference tags are extracted.
   - Note: the `tree-sitter-languages` collection has no swift query (confirmed), so
     fallback there is N/A; rely on the single language-pack query.

2. **flat-rank-fix: Run PageRank even without chat files**
   - File: `src/privrepomap/repomap.py` (`get_ranked_tags`, ~lines 372-378).
   - Run `nx.pagerank(graph, alpha=0.85)` when there is no personalization (instead of
     assigning flat 1.0), keeping personalization when chat files exist, and keeping the
     existing exception fallback to flat ranks.
   - Add a test asserting differentiated ranks on a graph with edges and no chat files.

3. **search-test-penalty (P1): De-prioritize test files for architectural queries**
   - File: `src/privrepomap/server.py` (`_run_search_identifiers`, sort key ~line 282).
   - Apply a secondary de-rank/penalty to matches in test paths
     (`*Tests.swift`, `/Tests/`, `*_test.*`, `test_*.py`, `*.spec.*`, etc.) so the
     canonical definition outranks test classes when scores tie or are flat.
   - Make it a defined helper (e.g. `_is_test_path`) reused where needed; keep defs
     before refs ordering intact.
   - Tests: assert `ThreeMatch`-style query surfaces the non-test definition first.

4. **primary-def-detection: Surface canonical definition first**
   - File: `src/privrepomap/server.py` (and/or repomap ranking helper).
   - When multiple files define the same identifier string, prefer the definitive
     declaration kind (`class`/`struct`/`enum`/`protocol`/`function` def) and
     non-test path as the primary result.
   - Tie-break before lexical/line ordering. Reuse the test-path helper from #3.
   - Tests: identifier defined in both a test and a source file returns source def #1.

5. **scope-globs (P2): Caller include/exclude control + source-only mode**
   - Files: `src/privrepomap/filescan.py`, `src/privrepomap/cli.py`,
     `src/privrepomap/server.py`.
   - Add optional `include_globs` / `exclude_globs` (and/or a `source_only` flag that
     excludes test paths) threaded from CLI args and MCP tool params down to
     `find_src_files` filtering. Default behavior unchanged when unset.
   - Keep all reads behind existing guards; globs only narrow, never bypass secret/size
     /binary/gitignore protections.
   - Tests: include/exclude globs correctly restrict the considered file set.

6. **report-diagnostics: Expose reference/graph density in reports**
   - Files: `src/privrepomap/repomap.py` (`FileReport`), `cli.py`, `server.py`.
   - Surface existing `reference_matches`/`definition_matches` prominently and add a
     derived signal (e.g. `references_extracted: bool` / edge count / "0 references
     extracted — ranking will be flat" note) in CLI verbose output and MCP report dicts.
   - Tests: report includes the new field; zero-ref case flagged.

7. **validate: Run full suite + manual Swift smoke check**
   - `pytest -q` (expect previously-24 passing + new tests).
   - `ruff check src tests`.
   - Optional manual: cold-cache `privrepomap` run on a Swift sample showing non-zero
     refs and differentiated ranks.

## Notes / Considerations

- **Privacy invariants are non-negotiable**: no network, no tiktoken, telemetry env
  vars stay set before FastMCP import in `server.py`, output stays redacted, stdout
  stays clean in MCP paths (stderr logging only).
- **Grammar risk for #1**: Swift reference capture node names must match the actual
  bundled tree-sitter-swift grammar; verify empirically before finalizing the query to
  avoid silently capturing nothing again.
- **Backward compatibility**: new CLI args / MCP params must be optional with current
  defaults preserved so existing behavior and tests are unaffected.
- **Keep cli.py and server.py aligned** when adding the scope/report features.
- Out of scope: fixing the original `repomap`/RepoMapper tool; upstream query
  contributions (mentioned in doc as ecosystem, not required here).
