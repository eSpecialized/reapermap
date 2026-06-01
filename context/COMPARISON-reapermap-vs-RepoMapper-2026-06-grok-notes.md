Fresh comparison complete. Significant changes (especially Swift reference extraction + PageRank fixes, search relevance work, scope controls, and test growth) were landed primarily in reapermap. I ran both tools cold-cache through the paces on bCandied2019 (the same large Swift/SpriteKit/Xcode project) using CLI + direct Python API invocations against the venvs for controlled metrics.

Key Empirical Results

Reference extraction (the P0 gap from the prior doc):
• reapermap (new): 3575 defs / 7181–10016 refs on full scans (208 files), references_extracted=True. The updated swift-tags.scm (user_type + call_expression + navigation_suffix patterns) now populates the MultiDiGraph. PageRank produces differentiated ranks.
• repomap (original): ~2450 defs / 0 refs (Swift query still only has definition patterns). Engine has partial ref handling from the "multimatch" update, but no edges on this codebase.

Search / ranking quality (with chat_files + mentioned_idents + source_only=True):
• Array2D: Canonical definition (UtilityExtensions/Array2D.swift) now correctly ranks #1 at ~0.295. Previously everything was flat 1.0 and test files often won.
• ThreeMatch / GameStateMachine / Potential / WarpSceneViewModel: Improved, but the large central WarpSceneViewModel.swift (heavy usage + chat boost) still dominates many top results for symbols that appear everywhere. Actual definition sites surface but can rank lower. The new relevance/penalty logic helps; more definition-site preference tuning would tighten this further.
• Search now returns real ranks instead of uniform values; source_only + globs + context params are effective new levers.

Stability & crashes:
• reapermap: Zero crashes across all runs (maps, full scans, searches, hygiene tests).
• repomap (original): Reproduced the exact prior crash (TypeError: expected string or buffer inside tiktoken during token counting). Still fragile on this project.

File discovery / hygiene (208 files on full root scan):
• reapermap: Excellent Xcode/Apple/agent resistance — 0 hits for DerivedData, build/, .claude/worktrees, Pods, *.xcodeproj, etc. Nested gitignore + secret/size/binary + SKIP globs all working. New --source-only / --include-glob / --exclude-glob give real control.
• Caveat (too much?): Broad root scan still surfaces many non-code files present in this repo (README.md, .swiftlint.yml, buildServer.json, .fods, bcandied-context/*.md reviews, .mmd diagrams, etc.). These are safe but can bloat the candidate pool and dilute maps unless you use the new scope flags. --source-only drops test files cleanly.
• Original remains weak here (naive discovery, prior scoping bugs).

Tests:
• reapermap: 47 passing (including new test_swift_refs.py that directly regresses the old P0 gap, plus redaction, scope, ranking, and security tests).
• repomap (original): Still 0 project tests.

Map output "feel" (1k–8k token runs, source-only):
• Classic dense Aider-style output (highest-ranked files first with lines-of-interest). With real centrality, the important engine/VM files surface properly when boosted. Feels purposeful rather than flat/lexical. The new tool is fast (sub-second ranking after initial parse on this size project) and fully offline.

MCP note: In this Grok session only the old "RepoMapper" server was connected (its two tools). The privrepomap / privrepomap-mcp entry point (your config snippet with the telemetry env vars) was not auto-discovered via the available search. All pacing was done via the documented CLI (privrepomap) + direct imports from the venv (privrepomap.server._run_search_identifiers, RepoMap.get_ranked_tags, etc.). This is actually the most precise way to measure the new implementation. The server.py + privrepomap-mcp binary exactly match the MCP surface you showed (async repo_map + search_identifiers with full ranking context params, force_refresh, source_only, etc.).

Updated Verdict

The changes delivered exactly the highest-leverage improvements the prior comparison called for.

• reapermap (privrepomap) is now a strong, stable, production-viable daily tool for Swift/Xcode projects like this one. The reference graph makes ranking meaningful; the scope controls address "too much" noise; privacy/offline/test/redaction posture remains excellent.
• Original repomap remains in the same degraded state (0 refs on Swift + crash + weak discovery + no tests). The gap has widened.

I wrote a full updated comparison document here (modeled directly on the one you referenced):

/Users/wthomps/source2025/reapermap/context/COMPARISON-reapermap-vs-RepoMapper-2026-06-update.md

It contains the detailed side-by-side table (new aggregate ~133/160 vs ~50/160), live numbers, "too little / too much" feel analysis, search examples, commands used, and updated recommendations.

If you want me to drill into any specific dimension (e.g., a particular search query with different boost combos, map output slices, the exact diff in the Swift query, or running the MCP server process directly), just say the word. The new tool is clearly performing well enough now for real work on this codebase.