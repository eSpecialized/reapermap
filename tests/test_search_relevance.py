"""Search-relevance tests: canonical definitions outrank test classes.

Covers the comparison-doc P1 items: de-prioritize test files and surface the
exact/canonical definition first for architectural identifier queries.
"""

from privrepomap.filescan import is_test_path
from privrepomap.server import _run_search_identifiers


def test_is_test_path_classification():
    assert is_test_path("bCandied2019Tests/LogicOnlyTests/ThreeMatchTests.swift")
    assert is_test_path("Tests/ButtonTests.swift")
    assert is_test_path("tests/test_foo.py")
    assert is_test_path("pkg/foo_test.go")
    assert is_test_path("src/widget.test.ts")
    assert is_test_path("src/widget.spec.js")
    # Non-test files (including tricky stems) must not be flagged.
    assert not is_test_path("src/Main/GameEngines/ThreeMatch.swift")
    assert not is_test_path("src/latest.py")
    assert not is_test_path("src/request.go")
    assert not is_test_path("app/contest.rb")


def test_canonical_definition_outranks_test_class(tmp_path):
    # Real definition, referenced by another source file.
    (tmp_path / "ThreeMatch.swift").write_text(
        "class ThreeMatch {\n    func process() {}\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "Engine.swift").write_text(
        "class Engine {\n"
        "    let match: ThreeMatch\n"
        "    init(match: ThreeMatch) { self.match = match }\n"
        "    func run() { match.process() }\n"
        "}\n",
        encoding="utf-8",
    )
    # Test class whose name merely contains the query string.
    tests_dir = tmp_path / "AppTests"
    tests_dir.mkdir()
    (tests_dir / "ThreeMatchTests.swift").write_text(
        "class ThreeMatchTests {\n    func testProcess() {}\n}\n",
        encoding="utf-8",
    )

    result = _run_search_identifiers(
        project_root=str(tmp_path),
        query="ThreeMatch",
        max_results=10,
        include_definitions=True,
        include_references=False,
    )

    assert "error" not in result
    results = result["results"]
    assert results, "no search results returned"
    # The canonical, non-test class definition must be the top hit.
    assert results[0]["file"] == "ThreeMatch.swift"
    assert results[0]["name"] == "ThreeMatch"
    assert not is_test_path(results[0]["file"])
