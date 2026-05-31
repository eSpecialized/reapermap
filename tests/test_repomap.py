"""End-to-end repomap and identifier search tests on the fixture repo."""

import asyncio
from pathlib import Path

from privrepomap.filescan import find_src_files, read_text
from privrepomap.repomap import RepoMap
from privrepomap.server import _run_search_identifiers, search_identifiers


def _mapper(root: Path) -> RepoMap:
    return RepoMap(map_tokens=4096, root=str(root), file_reader_func=read_text,
                   output_handler_funcs={"info": lambda *a: None,
                                         "warning": lambda *a: None,
                                         "error": lambda *a: None})


def test_map_generation(fixture_repo):
    mapper = _mapper(fixture_repo)
    others = find_src_files(str(fixture_repo))
    map_content, report = mapper.get_repo_map(other_files=others)

    assert map_content is not None
    assert "utils.py" in map_content or "main.py" in map_content
    assert report.definition_matches > 0


def test_map_is_token_bounded(fixture_repo):
    mapper = RepoMap(map_tokens=50, root=str(fixture_repo), file_reader_func=read_text,
                     output_handler_funcs={"info": lambda *a: None,
                                           "warning": lambda *a: None,
                                           "error": lambda *a: None})
    others = find_src_files(str(fixture_repo))
    map_content, _ = mapper.get_repo_map(other_files=others)
    if map_content:
        assert mapper.token_count(map_content) <= 50


def test_planted_secret_redacted_in_map(fixture_repo):
    mapper = _mapper(fixture_repo)
    others = find_src_files(str(fixture_repo))
    map_content, _ = mapper.get_repo_map(
        other_files=others, mentioned_idents={"load"}
    )
    assert map_content is not None
    # The fake AWS key inside config.py must not appear verbatim.
    assert "AKIAIOSFODNN7EXAMPLE" not in map_content


def test_identifier_search(fixture_repo):
    mapper = _mapper(fixture_repo)
    others = find_src_files(str(fixture_repo))
    all_tags = []
    for f in others:
        rel = str(Path(f).relative_to(fixture_repo))
        all_tags.extend(mapper.get_tags(f, rel))
    names = {t.name for t in all_tags}
    assert "greet" in names
    assert "add" in names


def test_search_identifiers_uses_ranking_and_returns_rank(tmp_path):
    """The MCP search tool now routes through get_ranked_tags so high-centrality defs win."""
    # Two files define "handleClick"; only one is referenced by other source.
    (tmp_path / "Button.swift").write_text(
        'func handleClick() { print("primary") }\n',
        encoding="utf-8",
    )
    (tmp_path / "App.swift").write_text(
        'import Button\nfunc onEvent() { handleClick() }\n',
        encoding="utf-8",
    )
    # Isolated decoy (no incoming refs in the graph) — should rank lower.
    (tmp_path / "Tests").mkdir()
    (tmp_path / "Tests" / "ButtonTests.swift").write_text(
        'func handleClick() { /* test double */ }\n',
        encoding="utf-8",
    )

    # Call the actual MCP tool function (async).
    result = asyncio.run(
        search_identifiers(
            project_root=str(tmp_path),
            query="handleClick",
            max_results=10,
            include_definitions=True,
            include_references=False,
        )
    )

    assert "error" not in result
    results = result["results"]
    assert len(results) >= 2

    # The primary (referenced) definition must appear before the isolated test double.
    primary = next((r for r in results if "App.swift" not in r["file"] and "Tests" not in r["file"]), None)
    test_double = next((r for r in results if "Tests" in r["file"]), None)

    assert primary is not None
    assert test_double is not None
    # Because of the reference edge, the primary file has higher PageRank.
    assert primary["rank"] >= test_double["rank"]
    # Report is now present (symmetry with repo_map).
    assert "report" in result
    assert result["report"]["total_files_considered"] >= 2


def test_run_search_identifiers_is_importable_sync_helper(tmp_path):
    """Regression coverage for callers that use the sync implementation directly."""
    (tmp_path / "thing.py").write_text("def useful_name():\n    return 1\n", encoding="utf-8")

    result = _run_search_identifiers(
        project_root=str(tmp_path),
        query="useful_name",
        max_results=5,
        include_definitions=True,
        include_references=False,
    )

    assert "error" not in result
    assert [item["name"] for item in result["results"]] == ["useful_name"]
