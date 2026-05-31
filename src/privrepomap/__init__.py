"""privrepomap — private, offline, structural repository mapper.

No network access, no telemetry. Structural code mapping via tree-sitter
tag extraction, a defs/refs graph, PageRank ranking, and token-budgeted
rendering, with secret redaction applied to all output.
"""

from .repomap import RepoMap, Tag, FileReport

__all__ = ["RepoMap", "Tag", "FileReport"]
__version__ = "0.1.0"
