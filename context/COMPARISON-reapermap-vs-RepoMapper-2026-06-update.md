# RepoMapper vs reapermap — Follow-up Comparative Analysis (Post Swift-Refs)

**Date**: 2026-06 (fresh run on current sources)  
**Author**: Grok 4.3  
**Context**: Significant changes landed since the 2026-05-31 comparison. Reapermap received "Add Swift reference extraction and fix non-functional PageRank", "Improve identifier search relevance for architectural queries", "Add scope controls and reference diagnostics", plus substantial test growth. The original RepoMapper received a "multimatch" update (engine reference handling) but its Swift query file was **not** extended.

**Test Subject**: `bCandied2019` — the same large iOS/Swift/SpriteKit/Xcode match-3 game codebase.

---

## Executive Summary

| Tool | Key New Metrics (full project, cold) | Verdict |
|------|--------------------------------------|---------|
| **repomap** (original) | 0 references, still crashes on tiktoken, no tests | Still degraded / unsuitable for this project |
| **reapermap** (privrepomap) | **7181–10016 references**, 47 passing tests, stable | **Clear winner and now usable day-to-day** |

**Primary advance**: The P0 gap identified in the prior comparison (Swift reference extraction) has been closed in reapermap. PageRank now produces meaningful differentiated ranks instead of flat 1.0 everywhere. The original received partial engine updates but still emits zero reference edges on Swift because its `swift-tags.scm` was not updated.

---

## Live Empirical Results on bCandied2019

### Reference Extraction (the game changer)
- **reapermap**: 3575 defs / **10016 refs** (full 208-file source-only-aware scan), `references_extracted=True`
- **repomap (original)**: ~2450 defs / **0 refs** (on comparable file set)

The new Swift query additions (user_type, call_expression, navigation_suffix captures) are successfully feeding the MultiDiGraph used for PageRank.

### Search / Ranking Quality (source_only=True + chat boost + mentioned)
- **Array2D**: Primary definition file now correctly surfaces at rank **0.295** (top result). Previously everything was 1.0 and test files often won.
- **ThreeMatch / GameStateMachine / Potential**: Still heavily surface *usage sites inside the large WarpSceneViewModel.swift* (the chat file) at very high boosted scores (~4.74). The actual definition sites (GameEngines/ThreeMatch.swift etc.) rank lower or require more aggressive source_only + explicit file boosts to promote.
- This is a classic "heavily-used central type" problem. The boost machinery works; further heuristics (definition-site preference for type names, intra-file usage down-weighting, or primary-def detection) are the next logical tuning step (already partially addressed in the "search relevance" PR).

### Stability & Error Handling
- **reapermap**: Zero crashes across all cold/warm runs, full scans, searches, and with --source-only / globs.
- **repomap (original)**: Reproduced the exact prior crash:
  ```
  TypeError: expected string or buffer
  ```
  inside tiktoken (during token counting on this Swift codebase). Still fragile.

### File Discovery Hygiene
- **reapermap**:
  - 208 source files on full root scan (after SKIP_DIRS + nested gitignore + secret/size/binary filters).
  - **0** pollution entries from DerivedData, build/, .claude/worktrees, Pods, *.xcodeproj, xcuserdata, etc.
  - New `--source-only` flag successfully drops *Tests.swift and test_* files when desired.
  - **Caveat (too much?)**: Broad root scan still pulls many non-code artifacts present in the repo root (README.md, .swiftlint.yml, buildServer.json, .fods spreadsheets, bcandied-context/*.md review files, .mmd diagrams). These bloat the candidate set for ranking and can dilute maps unless the caller uses `--source-only`, `--include-glob`, or `--exclude-glob`.
- **repomap (original)**: Still uses the naive discovery logic documented previously; scoping bugs and lack of Xcode-specific ignores remain.

### Performance & Caching
- Both tools are fast on this ~200-file project once the tree-sitter languages are warm (sub-second for ranking after the initial parse pass).
- reapermap's pure-Python PageRank + heuristic token counting avoids the heavy tiktoken import and any network risk.

### Test Coverage
- **reapermap**: **47 tests passing** (including the new `test_swift_refs.py` suite that specifically regresses the P0 gap from the prior comparison, plus security/redaction, scope, and ranking-behavior tests).
- **repomap (original)**: Still **zero project tests** (only vendored dependency tests in its venv).

---

## Updated Scoring (same 0–10 scale as prior doc, out of 160)

| Dimension | repomap (original) | reapermap (new) | Winner | Delta vs Prior |
|-----------|--------------------|-----------------|--------|----------------|
| File discovery hygiene | 2 | 9 | reapermap | No change |
| Pollution resistance (Xcode/agents) | 1 | 9 | reapermap | No change |
| **Reference extraction (graph edges)** | **3** | **9** | **reapermap** | **+6** (was tie at 3) |
| Ranking quality on maps | 4 | 8 | reapermap | +2 |
| `search_identifiers` quality | 2 | 7 | reapermap | +2 (now uses real ranks + scope controls) |
| Privacy / offline guarantees | 3 | 10 | reapermap | No change |
| Test coverage | 0 | 9 | reapermap | + (24 → 47) |
| Output redaction | 1 | 8 | reapermap | No change |
| Token estimation | 6 | 8 | reapermap | Slight (heuristic default) |
| MCP tool surface | 5 | 9 | reapermap | +1 (search now accepts full ranking context) |
| Error handling & diagnostics | 3 | 9 | reapermap | +1 |
| Code structure / maintainability | 4 | 9 | reapermap | No change |
| Documentation & review artifacts | 6 | 9 | reapermap | No change |
| Dependency hygiene | 4 | 9 | reapermap | No change |
| Observed behavior on this Xcode project | 2 | 8 | reapermap | +2 (no crash + real refs) |
| Swift/Xcode project support | 2 | 8 | reapermap | +3 |

**New Aggregate Scores** (out of 160):
- **repomap**: ~50 (31%) — essentially unchanged / still broken for this workload
- **reapermap**: **133** (~83%) — up from 118; now a strong practical tool for Swift/Xcode projects

---

## "Too Little / Too Much" Feel on Real Usage

**What now feels right (was too little):**
- Reference graph is populated → PageRank produces visibly different centrality scores.
- Architectural symbols like `Array2D` surface their canonical definition first when proper context/boosts are supplied.
- `source_only` + globs give the caller real control that was missing before.
- Diagnostics in the report (`references_extracted`, counts, excluded) make it obvious why ranking behaves the way it does.

**What can still feel like too much:**
- Default root scan is broad (208 files including many .md, .json, review docs). The map for the whole project at 8k tokens still has to pick a subset; callers should prefer explicit `chat_files` + `other_files` or `--source-only` for focused work.
- Identifier search returns *every* capture site for a name (including local vars `threeMatch`, `potential`, property wrappers, etc.). For very common identifiers inside a 2000-line central view model this produces long result lists even with ranking. The `max_results` + `source_only` + `mentioned_idents` knobs mitigate but do not eliminate the noise.

**What still feels like too little (shared or new):**
- The original tool remains unusable (crash + 0 refs).
- Even with refs, the search result ordering for "type used everywhere" symbols still favors the heavy-usage file over the definition file unless the definition file itself is explicitly boosted. This is the remaining relevance tuning surface (the recent "search relevance" work already moved the needle).

---

## Commands Used in This Comparison

```bash
# Clear
rm -rf .repomap.tags.cache.v1

# New tool (CLI)
privrepomap . --force-refresh --map-tokens 8192 --source-only --verbose

# New tool (python API for precise metrics + search)
python -c 'from privrepomap.server import _run_search_identifiers; ...'
python -c 'from privrepomap.repomap import RepoMap; ... ; mapper.get_ranked_tags(...)'

# Original tool (CLI — still crashes)
/usr/local/bin/repomap . --force-refresh --map-tokens 2048 --verbose

# Test suites
cd reapermap && python -m pytest -q          # 47 passed
# (original has no project tests)
```

---

## Recommendations (Updated)

### For reapermap (now highest-leverage items)
1. **Search result filtering for "type vs. usage"** — When the query matches a type name that has a clear primary definition, prefer the definition site(s) even if the chat file contains more occurrences. Consider a small definition-site bonus or separate "definition-only" result mode.
2. **Tighter default discovery or "code files only" preset** — The current broad scan + excellent ignore hygiene is safe but noisy for repos that contain lots of docs/review artifacts alongside source. Consider a `--code-only` or language-filtered default for the common case.
3. **Expose reference density / graph stats** in the MCP `repo_map` and `search_identifiers` reports (already partially present via FileReport).
4. Continue the excellent test and redaction discipline.

### For the original repomap
- The gap has widened. At minimum it needs the updated `swift-tags.scm` (with the three reference patterns) plus removal of the tiktoken hard dependency (or a safe fallback) to even be in the same conversation as reapermap on real Swift/Xcode work.

---

**Conclusion**: The "significant changes" delivered exactly the P0 capability the prior comparison called for. On this project, reapermap (privrepomap) has gone from "promising but limited by 0 refs" to "the clear daily driver for repository mapping and identifier search on Swift codebases." The original tool remains in the same degraded state documented previously.

Ready for further targeted tuning on search relevance or discovery presets if desired.
