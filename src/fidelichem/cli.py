"""Command-line interface for the FideliChem platform."""

from __future__ import annotations

import contextlib
import sys
from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

from fidelichem import __version__


def create_parser() -> ArgumentParser:
    """Create the root CLI argument parser with subcommands."""
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

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # GUI subcommand
    subparsers.add_parser("gui", help="Launch the FideliChem desktop application")

    # Probe subcommand
    probe_parser = subparsers.add_parser(
        "probe", help="Inspect and probe an evidence dataset without importing"
    )
    probe_parser.add_argument(
        "--adapter",
        "-a",
        type=str,
        default="auto",
        help="Adapter name (e.g. gold, smiles2docking, moldynstudio, or auto)",
    )
    probe_parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="Path to evidence folder or data file",
    )

    # Export subcommand
    export_parser = subparsers.add_parser(
        "export",
        help="Export processed project dataset to multi-format bundles",
    )
    export_parser.add_argument(
        "--project",
        "-p",
        type=str,
        required=False,
        help="Path to an existing FideliChem project workspace",
    )
    export_parser.add_argument(
        "--output",
        "-o",
        type=str,
        required=True,
        help="Target output directory",
    )
    export_parser.add_argument(
        "--formats",
        "-f",
        type=str,
        default="csv,json,methods_report",
        help="Formats (csv, json, xlsx, parquet, methods_report)",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the FideliChem command-line interface."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "gui":
        from fidelichem.gui.application import main as gui_main

        return gui_main()

    if args.subcommand == "probe":
        from fidelichem.adapters.registry import AdapterRegistry

        registry = AdapterRegistry.with_builtins()
        registry.discover_entry_points()
        adapter = registry.get(args.adapter) if args.adapter != "auto" else None
        in_path = Path(args.input)
        if not in_path.exists():
            sys.stderr.write(f"Error: Input path '{args.input}' does not exist.\n")
            return 1

        if adapter:
            probe_res = adapter.probe(in_path)
            sys.stdout.write(f"Adapter: {adapter.adapter_id}\n")
            sys.stdout.write(f"Confidence: {probe_res.confidence:.2f}\n")
            sys.stdout.write(f"Detected Format: {probe_res.detected_format}\n")
        else:
            probes = registry.probe_all(in_path)
            for p in probes:
                if p.confidence > 0.0:
                    msg = (
                        f"Detected: {p.suggested_adapter} "
                        f"(confidence {p.confidence:.2f}): {p.detected_format}\n"
                    )
                    sys.stdout.write(msg)
        return 0

    if args.subcommand == "export":
        if not args.project:
            sys.stderr.write(
                "Error: --project is required to export persisted evidence.\n"
            )
            return 2
        from fidelichem.exports.engine import ExportEngine
        from fidelichem.exports.models import ExportFormat, ExportOptions
        from fidelichem.projects.service import open_project

        try:
            paths = open_project(Path(args.project), read_only=True)
        except Exception:  # noqa: BLE001
            sys.stderr.write(
                "Error: project could not be opened; verify its manifest "
                "and database.\n"
            )
            return 1

        fmt_names = [f.strip().lower() for f in args.formats.split(",")]
        fmts: list[ExportFormat] = []
        for fn in fmt_names:
            with contextlib.suppress(ValueError):
                fmts.append(ExportFormat(fn))
        opts = ExportOptions(formats=tuple(fmts) if fmts else (ExportFormat.CSV,))

        try:
            if (
                paths.engine is None
                or paths.project_id is None
                or paths.project is None
            ):
                sys.stderr.write("Error: project has no readable database.\n")
                return 1
            from fidelichem.storage.session import UnitOfWork

            with UnitOfWork(paths.engine) as uow:
                records = list(uow.evidence.list_export_records(paths.project_id))
        finally:
            paths.close()

        if not records:
            sys.stderr.write(
                "Error: the project has no completed scientific evidence to export.\n"
            )
            return 1

        engine = ExportEngine()
        out_dir = Path(args.output)
        res = engine.export_dataset(
            project_name=paths.project.name,
            records=records,
            output_dir=out_dir,
            options=opts,
        )
        sys.stdout.write(f"Export completed: {res.manifest_path}\n")
        return 0

    return 0


__all__ = ["create_parser", "main"]
