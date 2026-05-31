# RepoMapper vs reapermap — Comparative Analysis

**Date**: 2026-05-31  
**Author**: Grok 4.3 analysis (fresh run)  
**Context**: Follow-up comparison after user refreshed repomapper caches/files and after Phase 1+2 hardening in reapermap (filescan improvements + search_identifiers now using ranked path).  
**Test Subject**: `bCandied2019` — large real-world iOS/Swift/SpriteKit/Xcode project (match-3 game engine + view models + extensive logic tests).

---

## Executive Summary

A side-by-side evaluation of the two repository-mapping tools on the same large Xcode/Swift codebase:

| Tool | Overall Score (out of 160) | Verdict for Daily Use on Xcode Projects |
|------|---------------------------|-----------------------------------------|
| **repomap** (original, `/usr/local/bin/repomap` from `RepoMapper` repo) | **52** (~33%) | Currently degraded / unsuitable |
| **reapermap** (`privrepomap` from `reapermap` repo) | **118** (~74%) | Usable today; clear winner but still has headroom |

**Primary reasons for the gap**:
- repomap's file discovery is dangerously naive and currently exhibits scoping bugs + runtime crashes on this project.
- reapermap has proper layered ignore logic, privacy guarantees, real tests (24 passing), and a hardened `search_identifiers` implementation.
- Both tools share the same critical weakness on Swift codebases: the `swift-tags.scm` query extracts **zero references**, collapsing PageRank to flat ranks.

---

## Methodology

- Both tools run **cold cache** (`--force-refresh`) against `/Users/wthomps/source2025/bCandied/bCandied2019`
- Identical token budgets tested (4096 and 8192)
- `search_identifiers` exercised on key architectural symbols (`ThreeMatch`, `WarpSceneViewModel`, `Array2D`, etc.)
- Static code review of core engines (`repomap_class.py` vs `src/privrepomap/repomap.py` + supporting modules)
- Test suite execution and dependency analysis
- Direct inspection of the installed `repomap` wrapper and the reapermap venv CLI/MCP entry points

---

## Detailed Feature Comparison

| Dimension | repomap (original) | reapermap (new) | Winner | Notes / "Too Much / Too Little" |
|-----------|--------------------|-----------------|--------|---------------------------------|
| **File discovery hygiene** | 2 | 9 | reapermap | repomap: extremely naive `find_src_files` (only skips dot-dirs + 4 hardcoded names). reapermap: defense-in-depth with `SKIP_DIRS`, globs, case-insensitive pruning, early `.gitignore` directory pruning, nested gitignore support, secret/size/binary filters. |
| **Pollution resistance** (build/, DerivedData/, .claude/worktrees/, Pods, *.xcodeproj, etc.) | 1 | 9 | reapermap | repomap: effectively zero protection. reapermap: explicit Xcode/Apple + agent/worktree entries + `SKIP_DIR_GLOBS`. |
| **Reference extraction (graph edges)** | 3 | 3 | Tie | **Shared failure**. Both use identical `swift-tags.scm` containing only definition patterns. Result on this project: 3575 defs / 0 refs. PageRank graph has no edges → flat ranking (all 1.0). |
| **Ranking quality on maps** | 4 | 6 | reapermap | repomap algorithm exists but is undermined by bad discovery and crashes. reapermap has same core + working boost machinery. |
| **`search_identifiers` quality** | 2 | 5 | reapermap | repomap: brute-force full walk + `get_tags` on every file, no ranking, no boosts, weak lexical sort. reapermap: now correctly routes through `get_ranked_tags()`, returns `rank` + `report`, accepts full context params. Still limited by 0 refs. |
| **Privacy / offline guarantees** | 3 | 10 | reapermap | repomap: depends on `tiktoken` (network risk), no redaction, no secret-file skipping. reapermap: deliberately offline (no tiktoken), socket-blocked test suite, 3-layer secret handling, full output redaction. |
| **Test coverage** | 0 | 9 | reapermap | repomap: **zero** project tests (only vendored dependency tests in venv). reapermap: 24 passing tests including offline proof, Xcode pollution tests, redaction tests, and ranking-behavior test for search. |
| **Output redaction** | 1 | 8 | reapermap | repomap: none. reapermap: `redact.py` with 10+ targeted patterns (AWS, GitHub, Stripe, JWT, PEM, generic key=secret, etc.). |
| **Token estimation** | 6 | 7 | reapermap (slight) | repomap: tiktoken (accurate but heavy). reapermap: heuristic (default) + optional pygments (fully offline). |
| **MCP tool surface** | 5 | 8 | reapermap | repomap: basic tools. reapermap: both `repo_map` and `search_identifiers` now accept `chat_files` / `mentioned_*` / `force_refresh`, return structured reports. |
| **Error handling & diagnostics** | 3 | 8 | reapermap | repomap: fragile (crashed during this comparison with tiktoken "expected string or buffer"). reapermap: consistent handlers + `FileReport` metadata. |
| **Code structure / maintainability** | 4 | 9 | reapermap | repomap: flat scripts, duplicated discovery logic, one giant class. reapermap: proper package layout, clear module boundaries, excellent internal documentation. |
| **Documentation & review artifacts** | 6 | 9 | reapermap | repomap: basic README. reapermap: README + `MAP.md`, `SECURITY.md`, `NOTICE`, detailed implementation reviews, prior comparison doc. |
| **Dependency hygiene** | 4 | 9 | reapermap | repomap: pulls tiktoken + networkx + diskcache + grep-ast. reapermap: same core trio but avoids tiktoken and telemetry paths. |
| **Observed behavior on this Xcode project (cold cache)** | 2 | 6 | reapermap | repomap: currently broken (scoping pollution + crashes). reapermap: produces output; architectural files surface but test files pollute searches due to missing references. |
| **Swift/Xcode project support** | 2 | 5 | reapermap | Both limited by weak Swift query. reapermap at least does not crash and has the ignore hardening required by real Xcode trees. |

**Aggregate Scores** (out of 160):
- **repomap**: 52 (33%)
- **reapermap**: 118 (74%)

---

## Live Run Observations (bCandied2019)

### repomap (original)
- Wrapper (`/usr/local/bin/repomap`) cd's into the RepoMapper source and injects `--root`.
- On cold run against bCandied2019 it produced output containing paths from inside the RepoMapper repo itself (scoping bug).
- Subsequent run crashed with:
  ```
  TypeError: expected string or buffer
  ```
  inside tiktoken during token counting.
- Effectively unusable in its current state on this project.

### reapermap (new)
- Successfully completed cold-cache runs at 4k and 8k token budgets.
- Example metrics from 8192-token run:
  - 16352 chars, ~4088 tokens
  - 3575 definition tags, **0 reference tags**
- `search_identifiers` for `ThreeMatch` (top 6):
  1. `bCandied2019Tests/LogicOnlyTests/ThreeMatchTests.swift:12` (rank 1.0)
  2. `bCandied2019Tests/LogicOnlyTests/ThreeMatchEngineTests.swift:12`
  3. `bCandied2019/Main/GameEngines/ThreeMatch.swift:13` ← real definition is #3
  4–6. More test files
- `search_identifiers` for `WarpSceneViewModel` returned only test classes in top results; the primary `WarpSceneViewModel.swift` definition did not appear in the first page.
- All ranks were 1.0 because the reference graph is empty.

---

## Critical Shared Weakness: Swift Reference Extraction

Both tools use the exact same `queries/tree-sitter-language-pack/swift-tags.scm`:

```scheme
(class_declaration name: (type_identifier) @name.definition.class) ...
(protocol_declaration ...)
(function_declaration name: (simple_identifier) @name.definition.function) ...
... only definition patterns exist
```

There are **no** `name.reference` captures for:
- Call sites
- Member access
- Type references in signatures / variables
- Protocol conformance
- Extensions
- Actor / struct / enum usage

**Impact**: PageRank has no edges → no meaningful centrality → test files and lexical order dominate identifier search results. This is the single largest remaining gap for using either tool effectively on Swift codebases.

---

## Recommendations & Prioritized Improvements

### For reapermap (highest leverage)

1. **Swift reference extraction (P0)**  
   Extend `swift-tags.scm` (and possibly fall back to the other query collection) to capture real references. This single change would make the existing ranking + boost machinery actually work on Xcode projects.

2. **Search result filtering / relevance tuning (P1)**  
   When reference data is present, prefer definitions that are referenced from high-rank files. Consider a small penalty or secondary sort for files under `Tests/`, `*Tests.swift`, etc., when the query is an architectural name.

3. **Better primary definition detection**  
   For common patterns (`class Foo`, `struct Foo`, `final class Foo`), ensure the canonical definition file surfaces first even when multiple files contain the same identifier string.

4. **Optional "source files only" mode or include/exclude globs on tools**  
   Give callers explicit control when the default discovery is still too noisy.

5. **Expose reference count or graph density in the report**  
   Let the caller see "0 references extracted" so they know why ranking feels flat.

### For repomap (original)

- The project appears largely unmaintained relative to reapermap.
- The installed version is currently in a worse state than when the first review was written.
- If it is to remain in service, it needs at minimum: proper gitignore-aware discovery, removal of tiktoken dependency, addition of output redaction, and a real test suite.

### Shared / Ecosystem

- Consider contributing improved `swift-tags.scm` (and other language queries) back to the common query collections if they are sourced from an upstream.
- Both tools would benefit from richer handling of Swift-specific constructs (extensions, actors, property wrappers, result builders, etc.).

---

## Open Questions for Further Analysis

- How much does the current Swift query miss on a typical modern Swift codebase? (We could instrument tag extraction counts per construct.)
- Would a lightweight post-processing step (simple regex or tree-sitter reference pass) be enough to bootstrap a usable graph even without perfect queries?
- What is the performance delta on warm cache for a 200+ file Xcode project between the two implementations?
- Should reapermap grow an explicit "Xcode project mode" that knows about `.xcodeproj` structure and derived data locations?

---

## Appendix: Commands Used in This Comparison

```bash
# Clear caches
rm -rf .repomap.tags.cache.v1

# Original tool (via installed wrapper)
/usr/local/bin/repomap . --force-refresh --map-tokens 8192 --verbose

# New tool (via venv)
/Users/wthomps/source2025/reapermap/.venv/bin/privrepomap . --force-refresh --map-tokens 8192 --verbose

# Search testing (via direct import for precision)
python -c 'from privrepomap.server import _run_search_identifiers; ...'
```

Full test suite (reapermap):
```bash
python -m pytest -q   # 24 passed
```

---

**Ready for review and improvement work.** Point me at any row, any score, any recommendation, or any part of the underlying code and I will propose concrete changes (or execute them).