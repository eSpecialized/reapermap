"""Secret redaction.

Applied to *all* rendered output before it leaves the process, so that even
if a secret slips past file-skipping (e.g. a credential hard-coded inside a
source file that is legitimately part of the map), it is masked.

This is heuristic, defense-in-depth — not a guarantee that every secret form
is caught. It errs toward redaction for well-known token shapes.
"""

from __future__ import annotations

import re
from typing import List, Pattern, Tuple

REDACTED = "[REDACTED]"

# Each rule is (compiled_pattern, replacement). Patterns that capture a prefix
# in group 1 preserve it and mask only the secret body.
_RULES: List[Tuple[Pattern[str], str]] = [
    # AWS access key id
    (re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}\b"), REDACTED),
    # AWS secret access key (assigned to a key-ish name)
    (
        re.compile(
            r"(?i)(aws_secret_access_key\s*[=:]\s*)['\"]?[A-Za-z0-9/+=]{40}['\"]?"
        ),
        r"\1" + REDACTED,
    ),
    # GitHub tokens
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"), REDACTED),
    # Slack tokens
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), REDACTED),
    # Google API key
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"), REDACTED),
    # Stripe keys
    (re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[0-9A-Za-z]{16,}\b"), REDACTED),
    # OpenAI-style keys
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), REDACTED),
    # JSON Web Token
    (
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"
        ),
        REDACTED,
    ),
    # Bearer / Authorization headers
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"), r"\1" + REDACTED),
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*)['\"]?[A-Za-z0-9._\-]{12,}['\"]?"),
        r"\1" + REDACTED,
    ),
    # Generic api key / secret / password / token assignments
    (
        re.compile(
            r"(?i)((?:api[_-]?key|secret|passwd|password|token|access[_-]?token)"
            r"\s*[=:]\s*)['\"]?[^'\"\s]{6,}['\"]?"
        ),
        r"\1" + REDACTED,
    ),
    # Private key PEM blocks (mask the body, keep the header/footer lines)
    (
        re.compile(
            r"(-----BEGIN [A-Z ]*PRIVATE KEY-----)"
            r".*?"
            r"(-----END [A-Z ]*PRIVATE KEY-----)",
            re.DOTALL,
        ),
        r"\1" + REDACTED + r"\2",
    ),
]


def redact(text: str) -> str:
    """Return ``text`` with recognized secrets masked.

    This is a heuristic defense-in-depth layer for rendered output. It covers
    common token shapes and assignment patterns but is not a formal guarantee
    that every possible secret representation will be removed.
    """
    if not text:
        return text
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text
