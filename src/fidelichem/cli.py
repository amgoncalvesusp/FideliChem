from argparse import ArgumentParser
from collections.abc import Sequence

from fidelichem import __version__


def create_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="fidelichem",
        description=(
            "Explainable multi-fidelity molecular evidence and decision platform"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    create_parser().parse_args(argv)
    return 0
