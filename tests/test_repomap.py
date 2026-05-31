"""End-to-end repomap and identifier search tests on the fixture repo."""

from pathlib import Path

from privrepomap.filescan import find_src_files, read_text
from privrepomap.repomap import RepoMap


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
