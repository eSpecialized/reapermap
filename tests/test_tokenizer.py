"""Offline tokenizer tests."""

from privrepomap.tokenizer import (
    count_tokens,
    estimate_tokens_heuristic,
    estimate_tokens_pygments,
)


def test_empty_is_zero():
    assert count_tokens("") == 0
    assert estimate_tokens_heuristic("") == 0
    assert estimate_tokens_pygments("") == 0


def test_heuristic_scales_with_length():
    short = count_tokens("a" * 8)
    long = count_tokens("a" * 80)
    assert long > short
    # ~chars/4
    assert count_tokens("a" * 40) == 10


def test_pygments_counts_code_tokens():
    code = "def f(x):\n    return x + 1\n"
    assert estimate_tokens_pygments(code) >= 5


def test_strategy_selection():
    code = "def f():\n    return 1\n"
    assert count_tokens(code, strategy="heuristic") > 0
    assert count_tokens(code, strategy="pygments") > 0
