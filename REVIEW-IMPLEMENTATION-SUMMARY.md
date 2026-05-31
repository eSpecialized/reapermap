# Review Implementation Summary — privrepomap

**Date**: April 2026  
**Context**: Follow-up to [GROK-REVIEW-Comparison.md](./GROK-REVIEW-Comparison.md)  
**Status**: Implementation of Phases 1 + 2 complete and locally verified. User validation on real Xcode project pending.

---

## Executive Summary

This work directly addresses the two highest-impact issues identified in the review of the new Python `privrepomap` server against the prior "old binary" on a real Xcode/Swift project (bCandied2019):

1. **Severe build/worktree pollution** in file discovery (`find_src_files`).
2. **Weak `search_identifiers`** that ignored the existing PageRank + boost ranking machinery.

**Outcome**:
- The discovery layer is now substantially harder against Xcode artifacts, `.claude/worktrees/`, `Derived*`, case-variant `Build/` directories, etc., while properly respecting both root and nested `.gitignore` files with early directory pruning.
- `search_identifiers` now routes through `get_ranked_tags()` (the same engine used by `repo_map`). Primary architectural definitions are strongly preferred over test doubles and generated noise.
- The MCP tool gained the same contextual boosting parameters (`chat_files`, `mentioned_idents`, etc.) already used with maps.
- All 23 tests pass (including 4 new high-value tests), the offline network-block suite remains green, and manual smoke tests on this repository show clean output with no pollution.

The changes are focused, preserve the strict privacy/offline guarantees, and require no new dependencies.

---

## Original Problems (from the Review)

Key excerpts from the review:

> **1. Build/ and worktree pollution is severe**
> - `build/` alone had 552 files (more than the entire source tree at 242 files).
> - `find_src_files` only skipped dot-dirs + a tiny hardcoded list. It did not respect `.gitignore` or skip Xcode build artifacts, `.claude/worktrees/`, `DerivedSources/`, etc.

> **2. `search_identifiers` is weak**
> - Searching for `WarpSceneViewModel` initially returned only test classes + build artifacts — completely missed the primary class definition.
> - It did a full project walk + `get_tags` on every file on every call (**no ranking, no smart scoping**).

> **Bottom line**: "Right now this new implementation is too noisy for comfortable daily use on a real Xcode/Swift project."

The review recommended exactly these two fixes:
- Proper ignore logic in `find_src_files`
- Make `search_identifiers` go through the ranked tag path

---

## What Was Implemented

### Phase 1 — Discovery & Ignore Hardening (`filescan.py`)

**Core changes**:
- Expanded `SKIP_DIRS` with comprehensive Xcode/Swift/Apple, worktree/agent, and common build/packaging directories (case variants included: `build` + `Build`).
- Added `SKIP_DIR_GLOBS` + `fnmatch` support (`Derived*`, `*.xcodeproj`, `*.xcworkspace`, etc.).
- **Case-insensitive** directory pruning on macOS (`d.lower()`).
- **Early directory pruning** using the gitignore `PathSpec` (prevents walking huge ignored trees).
- **Minimal nested `.gitignore` support** (chosen approach A): `_collect_gitignore_patterns()` finds all `.gitignore` files (via pruned walk), prefixes patterns from subdirectories (e.g. `Packages/MyLib/.gitignore` containing `build/` becomes correctly scoped), and produces one `PathSpec`. This makes the previous inaccurate docstring claim true.
- Always-ignore patterns (cache + secrets) remain defense-in-depth.
- Updated module and function docstrings + added a design comment block explaining the layered strategy.

**New tests** (in `tests/test_filescan.py`):
- `test_expanded_skip_dirs_and_globs_prune_xcode_artifacts` — realistic polluted tree with `Build/`, `DerivedData/`, `Pods/`, `.claude/worktrees/`, `*.xcodeproj`, etc.
- `test_nested_gitignore_is_respected` — root + nested `.gitignore` both honored.
- `test_respect_gitignore_false_still_applies_skip_and_secrets` — guarantees SKIP + secrets are never bypassed.

All existing tests continue to pass.

### Phase 2 — `search_identifiers` Now Uses Ranking (Option 1)

**Core changes** (in `server.py`):
- Extended the MCP tool signature (fully backward-compatible) with the same contextual parameters as `repo_map`:
  - `chat_files`, `other_files`, `mentioned_files`, `mentioned_idents`, `force_refresh`.
- Rewrote the inner `_run()`:
  - Computes effective file scope exactly like `repo_map`.
  - Calls `repo_mapper.get_ranked_tags(...)` — the ranked path requested in the review.
  - Builds a `file_rank` map from the scored definitions.
  - Matching definitions come pre-sorted from the ranked list.
  - References (when requested) receive the file's rank.
  - Final sort prefers high rank → defs before refs → lexical position.
  - Every result now includes `"rank": X.XXXX`.
  - A `report` object is returned for symmetry with `repo_map`.
- The tool now benefits from the same 5–20× boosts and PageRank centrality that already worked well for maps.

**New test** (in `tests/test_repomap.py`):
- `test_search_identifiers_uses_ranking_and_returns_rank` — creates a primary definition that is referenced + an isolated test double for the same name. Asserts the primary wins on rank and appears earlier. Also verifies the new `report` field.

All tests remain green (now 23 total).

---

## Files Changed

| File                              | Impact |
|-----------------------------------|--------|
| `src/privrepomap/filescan.py`     | Main discovery hardening (SKIP list, globs, case folding, dir pruning, nested gitignore collector) |
| `src/privrepomap/server.py`       | Tool signature extension + complete rewrite of `search_identifiers` `_run()` logic to use ranking |
| `tests/test_filescan.py`          | 3 new strong tests covering Xcode pollution, nested ignores, and `respect_gitignore=False` behavior |
| `tests/test_repomap.py`           | New test proving search now prefers high-centrality definitions |
| `MAP.md`                          | Updated architecture description |
| `INSTRUCTIONS.md`                 | Updated tool signatures + usage guidance for the new context parameters on search |

`git diff --shortstat` at the time of this summary: 6 files changed.

---

## Test & Verification Results

- **Full test suite**: 23 passed
- **Offline network-block suite** (`tests/test_offline.py`): 2 passed (still proves zero network access)
- **Filescan-specific tests**: 7 passed (including 3 new ones)
- **Manual CLI smoke** on this repository: clean output, no `build/`, `.egg-info`, or cache pollution surfaced
- **Import / runtime**: Both the CLI and MCP server import cleanly after changes

The new tests are realistic and directly derived from the failure modes described in the review.

---

## How the Original Complaints Are Now Addressed

| Review Complaint                        | How It Is Resolved |
|-----------------------------------------|--------------------|
| `build/` (552 files) leaking            | Expanded SKIP list (case-insensitive + globs) + early gitignore dir pruning |
| Xcode artifacts (`DerivedData`, `.claude/worktrees/`, `Pods`, etc.) leaking | Explicit entries in `SKIP_DIRS` + globs |
| `.gitignore` not respected (especially nested) | Full nested collection + prefixing + early dir pruning using the resulting spec |
| `search_identifiers` returned test/build noise first | Now uses `get_ranked_tags()` — only high-centrality files rank highly |
| Primary definitions (e.g. `WarpSceneViewModel`) buried | Same ranking + optional `mentioned_idents`/`chat_files` boosts now available on search |
| No way to pass context to search | New optional parameters mirror `repo_map` exactly |

---

## How to Validate on Your Xcode Project (Recommended Steps)

1. Pull the latest code.
2. In your target Xcode/Swift project, clear the tags cache:
   ```bash
   rm -rf .repomap.tags.cache.v1/
   ```
3. Restart the MCP server (`privrepomap-mcp`).
4. Re-run the **exact same queries** you used in the original review, especially:
   - `search_identifiers` for `WarpSceneViewModel` (and other key types/viewmodels)
   - `repo_map` at similar token budgets, with and without `chat_files`/`mentioned_idents`
5. Compare:
   - Signal density vs. noise (test files, build artifacts)
   - Whether the primary definition now appears in the top 1–5 results
   - Whether `rank` values are useful in the output
   - Any change in "feel" or token efficiency

Please report back with your observations (top results for the key identifier, whether build/ noise is visibly reduced, any surprises, latency notes, etc.). This real-world data on the original project is the final gate.

---

## Remaining / Follow-up Items

- **User validation** on the bCandied2019-style Xcode tree (the only item still in flight).
- Swift query coverage (`queries/.../swift-tags.scm`) was deliberately left as a separate, low-risk follow-up (the review's primary complaints were discovery + search ordering, not extraction completeness). Adding `struct_declaration`, `enum_declaration`, `actor`, extension methods, etc. would be a small subsequent improvement.
- Optional future niceties (not required for the review goals):
  - Richer include/exclude glob support on the tools
  - Even more complete nested gitignore negation handling (current approach is practical and sufficient for the 95% case)
  - Search-only fast path that skips PageRank when no context is supplied (currently unnecessary — graphs are tiny)

---

## Notes for Review

- All changes respect the project's hard constraints (zero network, no `tiktoken`, telemetry disabled before FastMCP import, secret handling at three layers, etc.).
- No changes were made to core ranking logic, `importance.py`, tokenizer, redact, or CLI behavior.
- The implementation followed the approved plan (see the session plan file for the detailed design decisions and pseudocode that were used).
- Backward compatibility was maintained for existing `repo_map` and `search_identifiers` callers.

---

**Ready for your review and real-project validation.** Once we have your feedback from the Xcode tree, we can decide whether any tweaks are needed or whether the old binary MCP configuration can be retired.

If you'd like this document adjusted (more/less detail, different structure, diff hunks included, etc.), just say the word.