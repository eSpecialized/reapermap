"""Unit tests for the pure-Python PageRank used for ranking.

These guard the root-cause bug where ``networkx.pagerank`` (SciPy/NumPy backend,
not a dependency here) raised at runtime and ranking silently went flat.
"""

import networkx as nx

from privrepomap.repomap import compute_pagerank


def test_pagerank_non_flat_on_directed_graph():
    g = nx.MultiDiGraph()
    g.add_edge("a", "hub")
    g.add_edge("b", "hub")
    g.add_edge("c", "hub")
    ranks = compute_pagerank(g)

    assert ranks["hub"] > ranks["a"]
    assert len({round(v, 9) for v in ranks.values()}) > 1


def test_pagerank_sums_to_one():
    g = nx.MultiDiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_edge("c", "a")
    ranks = compute_pagerank(g)
    assert abs(sum(ranks.values()) - 1.0) < 1e-6


def test_pagerank_parallel_edges_weighted():
    g = nx.MultiDiGraph()
    # Source ``a`` references ``hub`` via two identifiers but ``other`` via one,
    # so ``hub`` should receive a larger share of a's outgoing mass.
    g.add_edge("a", "hub")
    g.add_edge("a", "hub")
    g.add_edge("a", "other")
    ranks = compute_pagerank(g)
    assert ranks["hub"] > ranks["other"]


def test_pagerank_personalization_biases_target():
    g = nx.MultiDiGraph()
    g.add_edge("a", "b")
    g.add_edge("c", "d")
    plain = compute_pagerank(g)
    biased = compute_pagerank(g, personalization={"a": 1.0})
    assert biased["a"] > plain["a"]


def test_pagerank_empty_graph():
    assert compute_pagerank(nx.MultiDiGraph()) == {}


def test_pagerank_dangling_node_handled():
    g = nx.MultiDiGraph()
    g.add_edge("a", "b")  # b is dangling (no out edges)
    ranks = compute_pagerank(g)
    assert abs(sum(ranks.values()) - 1.0) < 1e-6
    assert all(v > 0 for v in ranks.values())
