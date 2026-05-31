"""Core repository-map engine.

Clean-room reimplementation of the structural repo-map design: extract
definition/reference tags with tree-sitter, build a defs->refs graph, rank
files with PageRank, then render a token-budgeted map using ``grep_ast``'s
``TreeContext``. All output is passed through secret redaction.

No network access and no telemetry are involved at any point.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from collections import defaultdict, namedtuple
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

import networkx as nx
from grep_ast import TreeContext

from .filescan import read_text
from .importance import filter_important_files
from .redact import redact
from .scm import get_scm_fname
from .tokenizer import count_tokens

# Tag for a parsed definition or reference.
Tag = namedtuple("Tag", "rel_fname fname line name kind")


@dataclass
class FileReport:
    """Summary of what was included/excluded when building a map."""

    excluded: Dict[str, str]
    definition_matches: int
    reference_matches: int
    total_files_considered: int


CACHE_VERSION = 1
TAGS_CACHE_DIRNAME = f".repomap.tags.cache.v{CACHE_VERSION}"
SQLITE_ERRORS = (sqlite3.OperationalError, sqlite3.DatabaseError)

# Ranking boosts.
BOOST_CHAT = 20.0
BOOST_MENTIONED_IDENT = 10.0
BOOST_MENTIONED_FNAME = 5.0
PERSONALIZATION_CHAT = 100.0


def _default_token_counter(text: str) -> int:
    return count_tokens(text, strategy="heuristic")


def compute_pagerank(
    graph: "nx.MultiDiGraph",
    personalization: Optional[Dict[str, float]] = None,
    alpha: float = 0.85,
    max_iter: int = 100,
    tol: float = 1.0e-6,
) -> Dict[str, float]:
    """Power-iteration PageRank over a ``MultiDiGraph``.

    Implemented in pure Python on purpose: ``networkx.pagerank`` routes through a
    SciPy/NumPy backend, which are intentionally *not* dependencies of this
    offline, minimal-footprint package. Without them ``nx.pagerank`` raises at
    runtime, which previously caused ranking to silently collapse to flat scores.

    Parallel edges between two nodes are summed into a single transition weight
    (i.e. the weight reflects the number of distinct shared identifiers between
    two files). Dangling nodes (no out-edges) redistribute their mass according
    to the teleport vector, matching standard PageRank semantics.
    """
    nodes = sorted(graph.nodes())
    n = len(nodes)
    if n == 0:
        return {}

    # Teleport / personalization vector ``p`` (normalized).
    if personalization:
        total = sum(max(0.0, personalization.get(node, 0.0)) for node in nodes)
        if total > 0.0:
            p = {node: max(0.0, personalization.get(node, 0.0)) / total for node in nodes}
        else:
            p = {node: 1.0 / n for node in nodes}
    else:
        p = {node: 1.0 / n for node in nodes}

    # Aggregate parallel edges into per-(u, v) weights and per-node out weight.
    edge_weights: Dict[Tuple[str, str], float] = defaultdict(float)
    for u, v in graph.edges():
        edge_weights[(u, v)] += 1.0

    out_adj: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    out_weight: Dict[str, float] = defaultdict(float)
    for (u, v), w in edge_weights.items():
        out_adj[u].append((v, w))
        out_weight[u] += w

    dangling_nodes = [node for node in nodes if out_weight[node] == 0.0]

    x = {node: 1.0 / n for node in nodes}
    for _ in range(max_iter):
        x_last = x
        x = {node: 0.0 for node in nodes}
        dangle_sum = alpha * sum(x_last[node] for node in dangling_nodes)
        for u in nodes:
            ow = out_weight[u]
            if ow <= 0.0:
                continue
            share = alpha * x_last[u] / ow
            for v, w in out_adj[u]:
                x[v] += share * w
        for node in nodes:
            x[node] += dangle_sum * p[node] + (1.0 - alpha) * p[node]
        err = sum(abs(x[node] - x_last[node]) for node in nodes)
        if err < n * tol:
            break
    return x


# Cache of (parser, query) per language, keyed by language name. Building a
# tree_sitter.Query is relatively expensive, so reuse across files.
_PARSER_QUERY_CACHE: Dict[str, tuple] = {}


def _get_parser_and_query(lang: str, language, scm_fname: str):
    """Build or reuse a local ``tree_sitter`` Parser and Query for ``lang``."""
    cached = _PARSER_QUERY_CACHE.get(lang)
    if cached is not None:
        return cached

    from tree_sitter import Parser, Query

    query_text = read_text(scm_fname, silent=True)
    if not query_text:
        _PARSER_QUERY_CACHE[lang] = (None, None)
        return None, None

    parser = Parser(language)
    query = Query(language, query_text)
    _PARSER_QUERY_CACHE[lang] = (parser, query)
    return parser, query


class RepoMap:
    """Generate ranked, token-budgeted maps for a repository.

    ``RepoMap`` is the shared engine behind the CLI and MCP server. It extracts
    tree-sitter tags, ranks definition sites from a defs/refs graph, renders
    source context, fits the result to a token budget, and redacts final map
    text before returning it.
    """

    def __init__(
        self,
        map_tokens: int = 1024,
        root: Optional[str] = None,
        token_counter_func: Callable[[str], int] = _default_token_counter,
        file_reader_func: Callable[[str], Optional[str]] = read_text,
        output_handler_funcs: Optional[Dict[str, Callable]] = None,
        repo_content_prefix: Optional[str] = None,
        verbose: bool = False,
        max_context_window: Optional[int] = None,
        map_mul_no_files: int = 8,
        refresh: str = "auto",
        exclude_unranked: bool = False,
    ):
        self.map_tokens = map_tokens
        self.max_map_tokens = map_tokens
        self.root = Path(root or os.getcwd()).resolve()
        self.token_count_func_internal = token_counter_func
        self.read_text_func_internal = file_reader_func
        self.repo_content_prefix = repo_content_prefix
        self.verbose = verbose
        self.max_context_window = max_context_window
        self.map_mul_no_files = map_mul_no_files
        self.refresh = refresh
        self.exclude_unranked = exclude_unranked

        if output_handler_funcs is None:
            output_handler_funcs = {"info": print, "warning": print, "error": print}
        self.output_handlers = output_handler_funcs

        self.tree_context_cache: Dict[str, TreeContext] = {}
        self.map_cache: Dict[tuple, Tuple[Optional[str], FileReport]] = {}

        self.load_tags_cache()

    # -- caching -----------------------------------------------------------

    def load_tags_cache(self) -> None:
        """Open the persistent tag cache, falling back to memory on failure."""
        cache_dir = self.root / TAGS_CACHE_DIRNAME
        try:
            import diskcache

            self.TAGS_CACHE = diskcache.Cache(str(cache_dir))
        except Exception as exc:  # pragma: no cover - fallback path
            self.output_handlers["warning"](f"Failed to load tags cache: {exc}")
            self.TAGS_CACHE = {}

    def tags_cache_error(self) -> None:
        """Recreate a corrupt tag cache or fall back to an in-memory cache."""
        try:
            cache_dir = self.root / TAGS_CACHE_DIRNAME
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            self.load_tags_cache()
        except Exception:  # pragma: no cover
            self.output_handlers["warning"](
                "Failed to recreate tags cache, using in-memory cache"
            )
            self.TAGS_CACHE = {}

    # -- token counting ----------------------------------------------------

    def token_count(self, text: str) -> int:
        """Count tokens, sampling long texts for speed."""
        if not text:
            return 0

        len_text = len(text)
        if len_text < 200:
            return self.token_count_func_internal(text)

        lines = text.splitlines(keepends=True)
        num_lines = len(lines)
        step = max(1, num_lines // 100)
        sample_text = "".join(lines[::step])
        if not sample_text:
            return self.token_count_func_internal(text)

        sample_tokens = self.token_count_func_internal(sample_text)
        est_tokens = (sample_tokens / len(sample_text)) * len_text
        return int(est_tokens)

    # -- path helpers ------------------------------------------------------

    def get_rel_fname(self, fname: str) -> str:
        """Return ``fname`` relative to the repo root when possible."""
        try:
            return str(Path(fname).relative_to(self.root))
        except ValueError:
            return fname

    def get_mtime(self, fname: str) -> Optional[float]:
        """Return file mtime, warning and returning ``None`` if missing."""
        try:
            return os.path.getmtime(fname)
        except FileNotFoundError:
            self.output_handlers["warning"](f"File not found: {fname}")
            return None

    # -- tag extraction ----------------------------------------------------

    def get_tags(self, fname: str, rel_fname: str) -> List[Tag]:
        """Return tags for a file, using the persistent cache when fresh."""
        file_mtime = self.get_mtime(fname)
        if file_mtime is None:
            return []

        try:
            cached_entry = self.TAGS_CACHE.get(fname)
            if cached_entry and cached_entry.get("mtime") == file_mtime:
                return cached_entry["data"]
        except SQLITE_ERRORS:
            self.tags_cache_error()

        tags = self.get_tags_raw(fname, rel_fname)

        try:
            self.TAGS_CACHE[fname] = {"mtime": file_mtime, "data": tags}
        except SQLITE_ERRORS:
            self.tags_cache_error()

        return tags

    def get_tags_raw(self, fname: str, rel_fname: str) -> List[Tag]:
        """Parse a file with tree-sitter and extract def/ref tags.

        Uses the pure ``tree_sitter`` Python API (``Parser`` + ``Query``)
        built from the language-pack ``Language`` object. The language-pack's
        own native parser is intentionally not used because its trees are not
        compatible with ``tree_sitter.Query``.
        """
        try:
            from grep_ast import filename_to_lang
            from grep_ast.tsl import get_language
            from tree_sitter import QueryCursor
        except ImportError:
            self.output_handlers["error"](
                "grep-ast and tree-sitter are required."
            )
            return []

        lang = filename_to_lang(fname)
        if not lang:
            return []

        scm_fname = get_scm_fname(lang)
        if not scm_fname:
            return []

        try:
            language = get_language(lang)
            parser, query = _get_parser_and_query(lang, language, scm_fname)
        except Exception as err:
            self.output_handlers["error"](f"Skipping file {fname}: {err}")
            return []

        if parser is None or query is None:
            return []

        code = self.read_text_func_internal(fname)
        if not code:
            return []

        try:
            tree = parser.parse(bytes(code, "utf-8"))
            captures = QueryCursor(query).captures(tree.root_node)

            tags: List[Tag] = []
            for capture_name, nodes in captures.items():
                if "name.definition" in capture_name:
                    kind = "def"
                elif "name.reference" in capture_name:
                    kind = "ref"
                else:
                    continue
                for node in nodes:
                    name = node.text.decode("utf-8") if node.text else ""
                    tags.append(
                        Tag(
                            rel_fname=rel_fname,
                            fname=fname,
                            line=node.start_point[0] + 1,
                            name=name,
                            kind=kind,
                        )
                    )
            return tags
        except Exception as exc:
            self.output_handlers["error"](f"Error parsing {fname}: {exc}")
            return []

    # -- ranking -----------------------------------------------------------

    def get_ranked_tags(
        self,
        chat_fnames: List[str],
        other_fnames: List[str],
        mentioned_fnames: Optional[Set[str]] = None,
        mentioned_idents: Optional[Set[str]] = None,
    ) -> Tuple[List[Tuple[float, Tag]], FileReport]:
        """Rank definition tags using PageRank over the defs/refs graph.

        Chat files seed personalization. Mentioned identifiers, mentioned
        files, and chat files then receive multiplicative boosts in the final
        per-tag score. The returned ``FileReport`` summarizes scan outcomes.
        """
        if not chat_fnames and not other_fnames:
            return [], FileReport({}, 0, 0, 0)

        if mentioned_fnames is None:
            mentioned_fnames = set()
        if mentioned_idents is None:
            mentioned_idents = set()

        def normalize_path(path: str) -> str:
            return str(Path(path).resolve())

        chat_fnames = [normalize_path(f) for f in chat_fnames]
        other_fnames = [normalize_path(f) for f in other_fnames]

        included: List[str] = []
        excluded: Dict[str, str] = {}
        total_definitions = 0
        total_references = 0

        defines: Dict[str, Set[str]] = defaultdict(set)
        references: Dict[str, Set[str]] = defaultdict(set)

        personalization: Dict[str, float] = {}
        chat_fnames_set = set(chat_fnames)
        chat_rel_fnames = set(self.get_rel_fname(f) for f in chat_fnames)

        all_fnames = list(set(chat_fnames + other_fnames))

        for fname in all_fnames:
            rel_fname = self.get_rel_fname(fname)

            if not os.path.exists(fname):
                excluded[fname] = "File not found"
                self.output_handlers["warning"](
                    f"Repo-map can't include {fname}: File not found"
                )
                continue

            included.append(fname)
            tags = self.get_tags(fname, rel_fname)

            for tag in tags:
                if tag.kind == "def":
                    defines[tag.name].add(rel_fname)
                    total_definitions += 1
                elif tag.kind == "ref":
                    references[tag.name].add(rel_fname)
                    total_references += 1

            if fname in chat_fnames_set:
                personalization[rel_fname] = PERSONALIZATION_CHAT

        graph = nx.MultiDiGraph()
        for fname in included:
            graph.add_node(self.get_rel_fname(fname))

        for name, ref_fnames in references.items():
            def_fnames = defines.get(name, set())
            for ref_fname in ref_fnames:
                for def_fname in def_fnames:
                    if ref_fname != def_fname:
                        graph.add_edge(ref_fname, def_fname, name=name)

        file_report = FileReport(
            excluded=excluded,
            definition_matches=total_definitions,
            reference_matches=total_references,
            total_files_considered=len(all_fnames),
        )

        if not graph.nodes():
            return [], file_report

        has_edges = graph.number_of_edges() > 0
        if not has_edges:
            # No references means no centrality signal; use flat ranks.
            ranks = {node: 1.0 for node in graph.nodes()}
        else:
            try:
                ranks = compute_pagerank(
                    graph,
                    personalization=personalization or None,
                    alpha=0.85,
                )
            except Exception as err:  # pragma: no cover - defensive
                self.output_handlers["warning"](
                    f"PageRank failed ({err}); falling back to flat ranks"
                )
                ranks = {node: 1.0 for node in graph.nodes()}

        ranked_tags: List[Tuple[float, Tag]] = []
        for fname in included:
            rel_fname = self.get_rel_fname(fname)
            file_rank = ranks.get(rel_fname, 0.0)

            if self.exclude_unranked and file_rank <= 0.0001:
                continue

            for tag in self.get_tags(fname, rel_fname):
                if tag.kind != "def":
                    continue
                boost = 1.0
                if tag.name in mentioned_idents:
                    boost *= BOOST_MENTIONED_IDENT
                if rel_fname in mentioned_fnames:
                    boost *= BOOST_MENTIONED_FNAME
                if rel_fname in chat_rel_fnames:
                    boost *= BOOST_CHAT
                ranked_tags.append((file_rank * boost, tag))

        ranked_tags.sort(key=lambda x: x[0], reverse=True)
        return ranked_tags, file_report

    # -- rendering ---------------------------------------------------------

    def render_tree(self, abs_fname: str, rel_fname: str, lois: List[int]) -> str:
        """Render lines-of-interest of a file using TreeContext."""
        code = self.read_text_func_internal(abs_fname)
        if not code:
            return ""

        try:
            if rel_fname not in self.tree_context_cache:
                self.tree_context_cache[rel_fname] = TreeContext(
                    rel_fname, code, color=False
                )
            return self.tree_context_cache[rel_fname].format(lois)
        except Exception:
            lines = code.splitlines()
            result_lines = [f"{rel_fname}:"]
            for loi in sorted(set(lois)):
                if 1 <= loi <= len(lines):
                    result_lines.append(f"{loi:4d}: {lines[loi - 1]}")
            return "\n".join(result_lines)

    def to_tree(self, tags: List[Tuple[float, Tag]]) -> str:
        """Render ranked tags into the textual map (highest-ranked first)."""
        if not tags:
            return ""

        file_tags: Dict[str, List[Tuple[float, Tag]]] = defaultdict(list)
        for rank, tag in tags:
            file_tags[tag.rel_fname].append((rank, tag))

        sorted_files = sorted(
            file_tags.items(),
            key=lambda x: max(rank for rank, _ in x[1]),
            reverse=True,
        )

        tree_parts: List[str] = []
        for rel_fname, file_tag_list in sorted_files:
            lois = [tag.line for _, tag in file_tag_list]
            abs_fname = str(self.root / rel_fname)
            max_rank = max(rank for rank, _ in file_tag_list)

            rendered = self.render_tree(abs_fname, rel_fname, lois)
            if not rendered:
                continue

            rendered_lines = rendered.splitlines()
            first_line = rendered_lines[0]
            code_lines = rendered_lines[1:]
            tree_parts.append(
                f"{first_line}\n(Rank value: {max_rank:.4f})\n\n"
                + "\n".join(code_lines)
            )

        return "\n\n".join(tree_parts)

    # -- map assembly ------------------------------------------------------

    def get_ranked_tags_map(
        self,
        chat_fnames: List[str],
        other_fnames: List[str],
        max_map_tokens: int,
        mentioned_fnames: Optional[Set[str]] = None,
        mentioned_idents: Optional[Set[str]] = None,
        force_refresh: bool = False,
    ) -> Tuple[Optional[str], FileReport]:
        """Return a cached token-budgeted map for the given file sets."""
        cache_key = (
            tuple(sorted(chat_fnames)),
            tuple(sorted(other_fnames)),
            max_map_tokens,
            tuple(sorted(mentioned_fnames or [])),
            tuple(sorted(mentioned_idents or [])),
        )

        if not force_refresh and cache_key in self.map_cache:
            return self.map_cache[cache_key]

        result = self.get_ranked_tags_map_uncached(
            chat_fnames, other_fnames, max_map_tokens,
            mentioned_fnames, mentioned_idents,
        )
        self.map_cache[cache_key] = result
        return result

    def get_ranked_tags_map_uncached(
        self,
        chat_fnames: List[str],
        other_fnames: List[str],
        max_map_tokens: int,
        mentioned_fnames: Optional[Set[str]] = None,
        mentioned_idents: Optional[Set[str]] = None,
    ) -> Tuple[Optional[str], FileReport]:
        """Build a token-budgeted map by binary-searching ranked tag count."""
        ranked_tags, file_report = self.get_ranked_tags(
            chat_fnames, other_fnames, mentioned_fnames, mentioned_idents
        )
        if not ranked_tags:
            return None, file_report

        # (Important files are computed for parity; ranking already biases
        # them via references, and they remain available for future tuning.)
        filter_important_files([self.get_rel_fname(f) for f in other_fnames])

        def try_tags(num_tags: int) -> Tuple[Optional[str], int]:
            if num_tags <= 0:
                return None, 0
            tree_output = self.to_tree(ranked_tags[:num_tags])
            if not tree_output:
                return None, 0
            return tree_output, self.token_count(tree_output)

        left, right = 0, len(ranked_tags)
        best_tree: Optional[str] = None
        while left <= right:
            mid = (left + right) // 2
            tree_output, tokens = try_tags(mid)
            if tree_output and tokens <= max_map_tokens:
                best_tree = tree_output
                left = mid + 1
            else:
                right = mid - 1

        return best_tree, file_report

    def get_repo_map(
        self,
        chat_files: Optional[List[str]] = None,
        other_files: Optional[List[str]] = None,
        mentioned_fnames: Optional[Set[str]] = None,
        mentioned_idents: Optional[Set[str]] = None,
        force_refresh: bool = False,
    ) -> Tuple[Optional[str], FileReport]:
        """Build and return the repository map plus file report metadata.

        This is the public engine entry point used by the CLI and MCP server.
        It handles empty inputs, optional budget expansion when there are no
        chat files, map-cache bypassing, ``RecursionError`` fallback, and final
        output redaction.
        """
        if chat_files is None:
            chat_files = []
        if other_files is None:
            other_files = []

        empty_report = FileReport({}, 0, 0, 0)
        if self.max_map_tokens <= 0 or not other_files:
            return None, empty_report

        max_map_tokens = self.max_map_tokens
        if not chat_files and self.max_context_window:
            padding = 1024
            available = self.max_context_window - padding
            max_map_tokens = min(max_map_tokens * self.map_mul_no_files, available)

        try:
            map_string, file_report = self.get_ranked_tags_map(
                chat_files, other_files, max_map_tokens,
                mentioned_fnames, mentioned_idents, force_refresh,
            )
        except RecursionError:
            self.output_handlers["error"]("Disabling repo map, git repo too large?")
            self.max_map_tokens = 0
            return None, empty_report

        if map_string is None:
            return None, file_report

        if self.verbose:
            tokens = self.token_count(map_string)
            self.output_handlers["info"](f"Repo-map: {tokens / 1024:.1f} k-tokens")

        other = "other " if chat_files else ""
        repo_content = ""
        if self.repo_content_prefix:
            repo_content = self.repo_content_prefix.format(other=other)
        repo_content += map_string

        # Defense-in-depth: redact secrets from all returned output.
        return redact(repo_content), file_report
