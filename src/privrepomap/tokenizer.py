"""Offline token estimation.

The original RepoMapper used ``tiktoken``, whose vocabulary is downloaded
from the network on first use. This module replaces it with a purely local
estimate so the tool never touches the network.

Two strategies are available:

* ``"heuristic"`` (default): a fast ``len(text) / CHARS_PER_TOKEN`` estimate.
  This is intentionally conservative and good enough for token-budgeting.
* ``"pygments"``: counts lexer tokens for the given text using Pygments,
  which ships its lexers locally (no network). Slightly more accurate for
  source code but slower.

Both are deterministic and offline.
"""

from __future__ import annotations

# Average characters per token for typical source code / English text.
# GPT-style BPE tokenizers land near ~4 chars/token; we use 4.0 as a stable
# default. This only needs to be in the right ballpark for budgeting.
CHARS_PER_TOKEN = 4.0


def estimate_tokens_heuristic(text: str) -> int:
    """Estimate token count using a chars-per-token heuristic."""
    if not text:
        return 0
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def estimate_tokens_pygments(text: str) -> int:
    """Estimate token count using a local Pygments lexer.

    Falls back to the heuristic if Pygments cannot lex the text. Pygments
    lexers are bundled with the package and require no network access.
    """
    if not text:
        return 0
    try:
        from pygments.lexers import guess_lexer
        from pygments.token import Token

        lexer = guess_lexer(text)
        count = 0
        for tok_type, value in lexer.get_tokens(text):
            if tok_type in Token.Text.Whitespace or not value.strip():
                continue
            count += 1
        return max(1, count)
    except Exception:
        return estimate_tokens_heuristic(text)


def count_tokens(text: str, strategy: str = "heuristic") -> int:
    """Count tokens offline.

    :param text: Text to measure.
    :param strategy: ``"heuristic"`` (default) or ``"pygments"``.
    """
    if strategy == "pygments":
        return estimate_tokens_pygments(text)
    return estimate_tokens_heuristic(text)
