#!/usr/bin/env python3
"""Command-line interface for privrepomap.

Generates a token-bounded structural map of a repository. Fully offline:
no network access, no telemetry. Output is secret-redacted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from .filescan import find_src_files, read_text
from .repomap import RepoMap
from .tokenizer import count_tokens


def _tool_output(*messages) -> None:
    print(*messages, file=sys.stdout)


def _tool_warning(message) -> None:
    print(f"Warning: {message}", file=sys.stderr)


def _tool_error(message) -> None:
    print(f"Error: {message}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the offline repository-map workflow."""
    parser = argparse.ArgumentParser(
        prog="privrepomap",
        description="Generate a private, offline structural map of a repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s .                         Map the current directory
  %(prog)s src/ --map-tokens 2048    Map src/ with a 2048-token budget
  %(prog)s --chat-files main.py .    Boost main.py, map the rest as context
        """,
    )
    parser.add_argument(
        "paths", nargs="*",
        help="Files or directories to include as other/context files.",
    )
    parser.add_argument(
        "project_root", nargs="?", default=None,
        help=argparse.SUPPRESS,  # accepted positionally via 'paths'
    )
    parser.add_argument(
        "--root", default=".",
        help="Repository root directory (default: current directory).",
    )
    parser.add_argument(
        "--map-tokens", type=int, default=8192,
        help="Maximum tokens for the generated map (default: 8192).",
    )
    parser.add_argument("--chat-files", nargs="*", help="Files in active context (highest boost).")
    parser.add_argument("--other-files", nargs="*", help="Other files to consider for the map.")
    parser.add_argument("--mentioned-files", nargs="*", help="Mentioned files (mid-level boost).")
    parser.add_argument("--mentioned-idents", nargs="*", help="Mentioned identifiers (boosted).")
    parser.add_argument(
        "--token-strategy", choices=["heuristic", "pygments"], default="heuristic",
        help="Offline token estimation strategy (default: heuristic).",
    )
    parser.add_argument("--max-context-window", type=int, help="Maximum context window size.")
    parser.add_argument("--force-refresh", action="store_true", help="Force refresh of caches.")
    parser.add_argument(
        "--include-glob", action="append", metavar="GLOB",
        help="Only include files matching this glob (repeatable). Narrows scan; "
             "never bypasses secret/size/binary/gitignore guards.",
    )
    parser.add_argument(
        "--exclude-glob", action="append", metavar="GLOB",
        help="Exclude files matching this glob (repeatable).",
    )
    parser.add_argument(
        "--source-only", action="store_true",
        help="Exclude test files/directories (e.g. *Tests.swift, test_*.py) from the scan.",
    )
    parser.add_argument(
        "--exclude-unranked", action="store_true",
        help="Exclude files with PageRank 0 from the map.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output.")
    return parser


def main(argv: List[str] | None = None) -> int:
    """Run the CLI and return a process-style exit code.

    Expands file/directory inputs with the privacy-aware scanner, constructs
    the shared ``RepoMap`` engine, and prints redacted map output to stdout.
    Diagnostics and verbose metadata go to stderr via the output handlers.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    output_handlers = {
        "info": _tool_output,
        "warning": _tool_warning,
        "error": _tool_error,
    }

    def token_counter(text: str) -> int:
        return count_tokens(text, strategy=args.token_strategy)

    # Determine the set of "other" path specs to expand into files.
    path_specs: List[str] = []
    if args.other_files:
        path_specs.extend(args.other_files)
    else:
        if args.paths:
            path_specs.extend(args.paths)
        if args.project_root:
            path_specs.append(args.project_root)
    if not path_specs:
        path_specs.append(args.root)

    effective_other_files: List[str] = []
    for spec in path_specs:
        effective_other_files.extend(
            find_src_files(
                spec,
                include_globs=args.include_glob,
                exclude_globs=args.exclude_glob,
                source_only=args.source_only,
            )
        )

    root_path = Path(args.root).resolve()
    chat_files = [str(Path(f).resolve()) for f in (args.chat_files or [])]
    chat_set = set(chat_files)
    other_files = [
        str(Path(f).resolve())
        for f in effective_other_files
        if str(Path(f).resolve()) not in chat_set
    ]

    mentioned_fnames = set(args.mentioned_files) if args.mentioned_files else None
    mentioned_idents = set(args.mentioned_idents) if args.mentioned_idents else None

    repo_map = RepoMap(
        map_tokens=args.map_tokens,
        root=str(root_path),
        token_counter_func=token_counter,
        file_reader_func=read_text,
        output_handler_funcs=output_handlers,
        verbose=args.verbose,
        max_context_window=args.max_context_window,
        exclude_unranked=args.exclude_unranked,
    )

    try:
        map_content, report = repo_map.get_repo_map(
            chat_files=chat_files,
            other_files=other_files,
            mentioned_fnames=mentioned_fnames,
            mentioned_idents=mentioned_idents,
            force_refresh=args.force_refresh,
        )
    except KeyboardInterrupt:
        _tool_error("Interrupted by user")
        return 1
    except Exception as exc:
        _tool_error(f"Error generating repository map: {exc}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1

    if map_content:
        if args.verbose:
            tokens = repo_map.token_count(map_content)
            _tool_output(
                f"Generated map: {len(map_content)} chars, ~{tokens} tokens, "
                f"{report.definition_matches} defs / {report.reference_matches} refs"
            )
            if not report.references_extracted:
                _tool_warning(
                    "0 references extracted — ranking will be flat. The language's "
                    "tags query may lack reference captures."
                )
        print(map_content)
    else:
        _tool_output("No repository map generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
