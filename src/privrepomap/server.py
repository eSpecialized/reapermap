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

from .filescan import find_src_files, read_text
from .redact import redact
from .repomap import RepoMap
from .tokenizer import count_tokens

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
        effective_other = find_src_files(str(root_path))

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
) -> Dict[str, Any]:
    """Search code identifiers by name (offline, secret-redacted).

    Use a bare identifier name (no prefixes/suffixes). The match is
    case-insensitive. Returns matches with file, line, kind, and context. The
    caller is trusted to provide an allowed local root and reasonable limits.

    :param project_root: Absolute path to the project root.
    :param query: Identifier name to search for.
    :param max_results: Maximum number of matches to return.
    :param context_lines: Lines of context around each match.
    :param include_definitions: Include definition matches.
    :param include_references: Include reference matches.
    :returns: ``{"results": [...]}`` or ``{"error": str}``.
    """
    if not os.path.isdir(project_root):
        return {"error": f"Project root directory not found: {project_root}"}

    root_path = Path(project_root).resolve()

    def _run() -> Dict[str, Any]:
        repo_mapper = RepoMap(
            root=str(root_path),
            token_counter_func=_token_counter,
            file_reader_func=read_text,
            output_handler_funcs={"info": log.info, "warning": log.warning, "error": log.error},
            verbose=False,
            exclude_unranked=True,
        )

        all_files = find_src_files(str(root_path))
        all_tags = []
        for file_path in all_files:
            try:
                rel_path = str(Path(file_path).relative_to(root_path))
            except ValueError:
                rel_path = file_path
            all_tags.extend(repo_mapper.get_tags(file_path, rel_path))

        query_lower = query.lower()
        matching = [
            tag for tag in all_tags
            if query_lower in tag.name.lower()
            and (
                (tag.kind == "def" and include_definitions)
                or (tag.kind == "ref" and include_references)
            )
        ]
        matching.sort(key=lambda t: (t.kind != "def", t.name.lower().find(query_lower)))
        matching = matching[:max_results]

        results = []
        for tag in matching:
            file_path = str(root_path / tag.rel_fname)
            start_line = max(1, tag.line - context_lines)
            end_line = tag.line + context_lines
            context = repo_mapper.render_tree(
                file_path, tag.rel_fname, list(range(start_line, end_line + 1))
            )
            if context:
                results.append({
                    "file": tag.rel_fname,
                    "line": tag.line,
                    "name": tag.name,
                    "kind": tag.kind,
                    "context": redact(context),
                })
        return {"results": results}

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        log.exception("Error searching identifiers")
        return {"error": f"Error searching identifiers: {exc}"}


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
