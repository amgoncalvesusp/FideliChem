"""GROMACS molecular dynamics analytical output evidence adapter."""

from .adapter import GromacsAdapter
from .xvg import XVGData, parse_xvg

__all__ = ["GromacsAdapter", "XVGData", "parse_xvg"]
