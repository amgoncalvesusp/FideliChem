"""Regression tests for GUI import adapter routing."""

from __future__ import annotations

from pathlib import Path

from fidelichem.gui.controller import WorkspaceController


def test_auto_import_resolves_a_supported_table_adapter(tmp_path: Path) -> None:
    source = tmp_path / "screen.txt"
    source.write_text("access_code\tsmiles\nEOS001\tCCO\n", encoding="utf-8")

    controller = WorkspaceController()

    assert controller._resolve_adapter_id("auto", source) == (
        "fidelichem.universal_table"
    )
