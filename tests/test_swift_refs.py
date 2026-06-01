"""Swift reference-extraction tests.

Regression coverage for the comparison-doc P0 gap: the Swift tags query used to
emit definitions only, leaving the defs->refs graph edgeless and collapsing
PageRank to flat ranks on Swift/Xcode projects.
"""

from pathlib import Path

from privrepomap.filescan import find_src_files, read_text
from privrepomap.repomap import RepoMap


def _mapper(root: Path) -> RepoMap:
    return RepoMap(
        map_tokens=4096,
        root=str(root),
        file_reader_func=read_text,
        output_handler_funcs={
            "info": lambda *a: None,
            "warning": lambda *a: None,
            "error": lambda *a: None,
        },
    )


def _swift_repo(tmp_path: Path) -> Path:
    (tmp_path / "Array2D.swift").write_text(
        "struct Array2D {\n"
        "    func count() -> Int { return 0 }\n"
        "    func clear() {}\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "ThreeMatch.swift").write_text(
        "class ThreeMatch {\n"
        "    func process() {}\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "Board.swift").write_text(
        "protocol Drawable {\n"
        "    func draw()\n"
        "}\n\n"
        "class Board: Drawable {\n"
        "    var grid: Array2D\n"
        "    let engine: ThreeMatch\n\n"
        "    init(engine: ThreeMatch) {\n"
        "        self.engine = engine\n"
        "        self.grid = Array2D()\n"
        "    }\n\n"
        "    func draw() {\n"
        "        engine.process()\n"
        "        grid.clear()\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    return tmp_path


def test_swift_references_extracted(tmp_path):
    repo = _swift_repo(tmp_path)
    mapper = _mapper(repo)
    tags = mapper.get_tags_raw(str(repo / "Board.swift"), "Board.swift")
    ref_names = {t.name for t in tags if t.kind == "ref"}

    assert any(t.kind == "ref" for t in tags), "Swift query extracted no references"
    # Type references (annotations / conformance) and call sites.
    assert {"Array2D", "ThreeMatch", "Drawable"} <= ref_names
    assert {"process", "clear"} <= ref_names


def test_swift_graph_has_edges_and_ranks(tmp_path):
    repo = _swift_repo(tmp_path)
    mapper = _mapper(repo)
    others = find_src_files(str(repo))
    ranked, report = mapper.get_ranked_tags(chat_fnames=[], other_fnames=others)

    assert report.reference_matches > 0
    assert ranked, "no ranked tags produced"
    # With cross-file edges and the no-chat PageRank path, ranks must vary.
    ranks = {round(score, 6) for score, _ in ranked}
    assert len(ranks) > 1, "ranks are flat; graph produced no useful centrality"


def test_references_extracted_report_flag(tmp_path):
    repo = _swift_repo(tmp_path)
    mapper = _mapper(repo)
    others = find_src_files(str(repo))
    _, report = mapper.get_ranked_tags(chat_fnames=[], other_fnames=others)
    assert report.references_extracted is True

    # A lone definition-only file extracts no references.
    (tmp_path / "Lonely.swift").write_text("class Lonely {}\n", encoding="utf-8")
    _, solo = mapper.get_ranked_tags(
        chat_fnames=[], other_fnames=[str(tmp_path / "Lonely.swift")]
    )
    assert solo.references_extracted is False
