#!/usr/bin/env python3
"""FastMCP server exposing privrepomap as offline MCP tools.

Tools:
  * ``repo_map`` — generate a token-bounded structural repository map.
  * ``search_identifiers`` — search code definitions/references by name.

Privacy: stateless stdio transport, telemetry disabled, all output redacted.
No network calls are made.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Disable FastMCP / framework telemetry before importing it.
os.environ.setdefault("FASTMCP_DISABLE_TELEMETRY", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

from fastmcp import FastMCP, settings

from .filescan import find_src_files, is_test_path, read_text
from .redact import redact
from .repomap import RepoMap
from .tokenizer import count_tokens

# Multiplier applied to a match's rank when it lives in a test file, so that
# canonical (non-test) definitions win for architectural identifier searches.
TEST_PATH_RANK_PENALTY = 0.1

# Logging: errors only, to stderr (stdout is the MCP channel).
logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("privrepomap.server")
logging.getLogger("fastmcp").setLevel(logging.ERROR)

settings.stateless_http = True

mcp = FastMCP("PrivRepoMapServer")


def _token_counter(text: str) -> int:
    return count_tokens(text, strategy="heuristic")


@mcp.tool()
async def repo_map(
    project_root: str,
    chat_files: Optional[List[str]] = None,
    other_files: Optional[List[str]] = None,
    token_limit: Any = 8192,
    exclude_unranked: bool = False,
    force_refresh: bool = False,
    mentioned_files: Optional[List[str]] = None,
    mentioned_idents: Optional[List[str]] = None,
    verbose: bool = False,
    max_context_window: Optional[int] = None,
    include_globs: Optional[List[str]] = None,
    exclude_globs: Optional[List[str]] = None,
    source_only: bool = False,
) -> Dict[str, Any]:
    """Generate a structural repository map (offline, secret-redacted).

    Provide filenames relative to ``project_root``. Files passed in
    ``chat_files`` get the highest ranking boost, ``mentioned_files`` a
    mid-level boost, and ``other_files`` a lower one. When ``other_files`` is
    omitted the project root is scanned (respecting ``.gitignore`` and
    skipping secrets). The caller is trusted to provide an allowed local root;
    this tool does not implement sandboxing or authorization.

    :param project_root: Absolute path to the project root.
    :param chat_files: Files in active context (highest boost).
    :param other_files: Other relevant files (lower boost).
    :param token_limit: Max tokens for the map (default 8192).
    :param exclude_unranked: Drop PageRank-0 files when True.
    :param force_refresh: Bypass the in-memory map cache.
    :param mentioned_files: Files mentioned in conversation (mid boost).
    :param mentioned_idents: Identifiers mentioned in conversation (boosted).
    :param verbose: Verbose logging.
    :param max_context_window: Used to scale the budget when no chat files.
    :param include_globs: Only scan files matching these globs (when scanning).
    :param exclude_globs: Skip files matching these globs (when scanning).
    :param source_only: Skip test files/directories (when scanning).
    :returns: ``{"map": str, "report": {...}}`` or ``{"error": str}``.
    """
    if not os.path.isdir(project_root):
        return {"error": f"Project root directory not found: {project_root}"}

    try:
        token_limit_int = int(token_limit) if token_limit else 8192
    except (TypeError, ValueError):
        token_limit_int = 8192
    if token_limit_int <= 0:
        token_limit_int = 8192

    chat_files_list = chat_files or []
    mentioned_fnames_set = set(mentioned_files) if mentioned_files else None
    mentioned_idents_set = set(mentioned_idents) if mentioned_idents else None

    root_path = Path(project_root).resolve()

    if other_files:
        effective_other = [str(root_path / f) for f in other_files]
    else:
        effective_other = find_src_files(
            str(root_path),
            include_globs=include_globs,
            exclude_globs=exclude_globs,
            source_only=source_only,
        )

    abs_chat_files = [str(root_path / f) for f in chat_files_list]
    chat_set = set(abs_chat_files)
    abs_other_files = [f for f in effective_other if f not in chat_set]

    if not abs_chat_files and not abs_other_files:
        return {"map": "No files found to generate a map."}

    try:
        repo_mapper = RepoMap(
            map_tokens=token_limit_int,
            root=str(root_path),
            token_counter_func=_token_counter,
            file_reader_func=read_text,
            output_handler_funcs={"info": log.info, "warning": log.warning, "error": log.error},
            verbose=verbose,
            exclude_unranked=exclude_unranked,
            max_context_window=max_context_window,
        )
    except Exception as exc:
        log.exception("Failed to initialize RepoMap")
        return {"error": f"Failed to initialize RepoMap: {exc}"}

    try:
        map_content, file_report = await asyncio.to_thread(
            repo_mapper.get_repo_map,
            chat_files=abs_chat_files,
            other_files=abs_other_files,
            mentioned_fnames=mentioned_fnames_set,
            mentioned_idents=mentioned_idents_set,
            force_refresh=force_refresh,
        )
    except Exception as exc:
        log.exception("Error generating repository map")
        return {"error": f"Error generating repository map: {exc}"}

    report_dict = {
        "excluded": file_report.excluded,
        "definition_matches": file_report.definition_matches,
        "reference_matches": file_report.reference_matches,
        "references_extracted": file_report.references_extracted,
        "total_files_considered": file_report.total_files_considered,
    }
    return {
        "map": map_content or "No repository map could be generated.",
        "report": report_dict,
    }


@mcp.tool()
async def search_identifiers(
    project_root: str,
    query: str,
    max_results: int = 50,
    context_lines: int = 2,
    include_definitions: bool = True,
    include_references: bool = True,
    # New optional context params (mirrors repo_map) so ranking + boosts can be applied.
    chat_files: Optional[List[str]] = None,
    other_files: Optional[List[str]] = None,
    mentioned_files: Optional[List[str]] = None,
    mentioned_idents: Optional[List[str]] = None,
    force_refresh: bool = False,
    source_only: bool = False,
) -> Dict[str, Any]:
    """Search code identifiers by name (offline, secret-redacted).

    Use a bare identifier name (no prefixes/suffixes). The match is
    case-insensitive. When chat_files / mentioned_* are supplied the results
    are ranked using the same PageRank + boost machinery as repo_map, so
    primary architectural definitions surface first. Exact-name matches and
    non-test files are preferred, so canonical definitions outrank test classes.

    :param project_root: Absolute path to the project root.
    :param query: Identifier name to search for.
    :param max_results: Maximum number of matches to return.
    :param context_lines: Lines of context around each match.
    :param include_definitions: Include definition matches.
    :param include_references: Include reference matches.
    :param chat_files: Files in active context (highest boost for ranking).
    :param other_files: Explicit file list to restrict the search scope.
    :param mentioned_files: Mentioned files (mid boost).
    :param mentioned_idents: Mentioned identifiers (strong boost for exact name matches).
    :param force_refresh: Bypass in-memory caches (tags are still mtime-based).
    :param source_only: Restrict the scan to non-test files.
    :returns: ``{"results": [...], "report": {...}}`` or ``{"error": str}``.
    """
    try:
        return await asyncio.to_thread(
            _run_search_identifiers,
            project_root=project_root,
            query=query,
            max_results=max_results,
            context_lines=context_lines,
            include_definitions=include_definitions,
            include_references=include_references,
            chat_files=chat_files,
            other_files=other_files,
            mentioned_files=mentioned_files,
            mentioned_idents=mentioned_idents,
            force_refresh=force_refresh,
            source_only=source_only,
        )
    except Exception as exc:
        log.exception("Error searching identifiers")
        return {"error": f"Error searching identifiers: {exc}"}


def _run_search_identifiers(
    project_root: str,
    query: str,
    max_results: int = 50,
    context_lines: int = 2,
    include_definitions: bool = True,
    include_references: bool = True,
    chat_files: Optional[List[str]] = None,
    other_files: Optional[List[str]] = None,
    mentioned_files: Optional[List[str]] = None,
    mentioned_idents: Optional[List[str]] = None,
    force_refresh: bool = False,
    source_only: bool = False,
) -> Dict[str, Any]:
    """Synchronous implementation for search_identifiers."""
    if not os.path.isdir(project_root):
        return {"error": f"Project root directory not found: {project_root}"}
    root_path = Path(project_root).resolve()

    repo_mapper = RepoMap(
        root=str(root_path),
        token_counter_func=_token_counter,
        file_reader_func=read_text,
        output_handler_funcs={"info": log.info, "warning": log.warning, "error": log.error},
        verbose=False,
        # Keep all matching definitions for recall: with working PageRank an
        # unreferenced definition can fall below the unranked threshold, so we
        # rely on the result ordering (exact-match + test penalty) instead of
        # dropping low-rank files outright.
        exclude_unranked=False,
    )

    # Determine effective file scope (same logic as repo_map).
    chat_list = chat_files or []
    abs_chat_files = [str(root_path / f) for f in chat_list]
    chat_set = set(abs_chat_files)

    if other_files:
        effective_other = [str(root_path / f) for f in other_files]
    else:
        effective_other = find_src_files(str(root_path), source_only=source_only)

    abs_other_files = [f for f in effective_other if f not in chat_set]

    mentioned_fnames_set = set(mentioned_files) if mentioned_files else None
    mentioned_idents_set = set(mentioned_idents) if mentioned_idents else None

    # Go through the ranked path (the key fix for the review complaint).
    # This gives us PageRank + chat/mentioned boosts for free.
    ranked_defs, file_report = repo_mapper.get_ranked_tags(
        abs_chat_files, abs_other_files, mentioned_fnames_set, mentioned_idents_set
    )

    # Build a quick lookup of the best rank per file (post-boost).
    file_rank: Dict[str, float] = {}
    for score, tag in ranked_defs:
        rel = tag.rel_fname
        if rel not in file_rank or score > file_rank[rel]:
            file_rank[rel] = score

    query_lower = query.lower()

    # Matching defs come from the already-ranked list (best first).
    scored: List[tuple] = []
    if include_definitions:
        for score, tag in ranked_defs:
            if query_lower in tag.name.lower():
                scored.append((score, tag, "def"))

    # Refs (if requested) require a second pass over the effective files;
    # they get the file's rank (no per-ref boost) so architectural context still wins.
    if include_references:
        all_files_for_refs = abs_chat_files + abs_other_files
        for fp in all_files_for_refs:
            try:
                rel = str(Path(fp).relative_to(root_path))
            except ValueError:
                rel = fp
            for tag in repo_mapper.get_tags(fp, rel):
                if tag.kind == "ref" and query_lower in tag.name.lower():
                    fr = file_rank.get(tag.rel_fname, 0.0)
                    scored.append((fr, tag, "ref"))

    # Final ordering balances three signals:
    #   1. Exact identifier match (canonical definition) outranks substring hits,
    #      so e.g. `ThreeMatch` beats `ThreeMatchTests` for the query "ThreeMatch".
    #   2. PageRank/boost score, penalized for test files so non-test definitions
    #      surface first on architectural queries.
    #   3. Definitions before references, then match position and line.
    def _sort_key(item: tuple) -> tuple:
        raw_score, tag, kind = item
        is_test = is_test_path(tag.rel_fname)
        adjusted = raw_score * (TEST_PATH_RANK_PENALTY if is_test else 1.0)
        exact = 0 if tag.name.lower() == query_lower else 1
        return (
            exact,
            -adjusted,
            0 if kind == "def" else 1,
            tag.name.lower().find(query_lower),
            tag.line,
        )

    scored.sort(key=_sort_key)
    scored = scored[:max_results]

    results = []
    for score, tag, kind in scored:
        abs_f = str(root_path / tag.rel_fname)
        start_line = max(1, tag.line - context_lines)
        end_line = tag.line + context_lines
        context = repo_mapper.render_tree(abs_f, tag.rel_fname, list(range(start_line, end_line + 1)))
        if context:
            results.append(
                {
                    "file": tag.rel_fname,
                    "line": tag.line,
                    "name": tag.name,
                    "kind": kind,
                    "context": redact(context),
                    "rank": round(score, 4),
                }
            )

    report = {
        "total_files_considered": file_report.total_files_considered,
        "definition_matches": file_report.definition_matches,
        "reference_matches": file_report.reference_matches,
        "references_extracted": file_report.references_extracted,
    }
    return {"results": results, "report": report}


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
