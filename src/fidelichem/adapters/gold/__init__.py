"""GOLD docking adapter package for CCDC GOLD runs, configurations, and poses."""

from .adapter import GoldAdapter
from .parsers import (
    parse_gold_conf,
    parse_gold_mol2,
    parse_gold_ranking,
)

__all__ = [
    "GoldAdapter",
    "parse_gold_conf",
    "parse_gold_mol2",
    "parse_gold_ranking",
]
