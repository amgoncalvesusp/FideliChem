"""Scientific scoring registry, comparability, and statistical normalization."""

from .normalizer import ScoreNormalizer
from .registry import ScoreRegistry

__all__ = [
    "ScoreNormalizer",
    "ScoreRegistry",
]
