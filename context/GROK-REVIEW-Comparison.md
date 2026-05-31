Q) I'm trying out a repomapper I had Opus 4.8 build, lets ditch the mcp configuration for the old one, and lets start using this new one

R) grok cli;
Results

It works (after the cache purge), but the "feel" and information quality are noticeably worse than the old binary for this project.

Key Observations

1. Build/ and worktree pollution is severe
• build/ alone has 552 files (more than the entire bCandied2019/ source tree at 242 files).
• The server's find_src_files only skips dot-dirs + a tiny hardcoded list (node_modules, __pycache__, venv, env). It does not respect .gitignore or skip Xcode build artifacts, .claude/worktrees/, DerivedSources/, etc.
• This noise leaks into both repo_map and especially search_identifiers.

2. search_identifiers is weak
• Searching for WarpSceneViewModel initially returned only test classes + build artifacts — completely missed the primary class definition in WarpSceneViewModel.swift.
• It does a full project walk + get_tags on every file on every call (no ranking, no smart scoping). The old binary was clearly using a more refined index.

3. Ranking with chat_files + mentioned_idents does work
• Boosts are applied (e.g. Array2D and scanForMatch jumped to rank 10.0 when mentioned).
• The output format includes explicit rank values, which is useful.
• However, the extra noise from build/ files still dilutes the value within the token budget.

4. Performance / latency
• Cold cache (force_refresh): acceptable but slower than the old native binary.
• Warm cache: fine.
• The identifier search path feels particularly heavy because it re-scans everything every time.

5. Side-by-side "feel"
• Old binary (when invoked correctly from project root): higher signal density, better implicit filtering, more architectural files surfaced early for the same token budget.
• New server: more verbose, more test files, build junk, and lower-quality identifier search. The structured report (definition_matches, excluded, etc.) is a nice addition, but the actual content is noisier.

Bottom Line

Right now this new implementation is too noisy for comfortable daily use on a real Xcode/Swift project like this one. The core ranking/PageRank logic appears sound, and the MCP surface is clean, but the file discovery and identifier search layers need real hardening before it feels like a replacement.

The most impactful fixes needed in the new server:
• Proper ignore logic in find_src_files (.gitignore + hard-coded build/ artifacts, .claude/, etc.)
• Make search_identifiers go through the ranked tag path instead of brute-force scanning
• Possibly expose an "only source files" mode or let the caller pass explicit include globs

Want me to open the new RepoMapper source and propose concrete patches for the ignore + search issues? Or run any other specific comparison scenarios?


# handed over to grok and asked to plan changes
