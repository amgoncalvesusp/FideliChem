"""Storage, retrieval, and heuristic header matching for table mapping presets."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

from fidelichem.domain.table_importer import TableMappingPreset


def _slugify(name: str) -> str:
    """Generate safe filename slug from preset name."""
    slug = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "_", slug) or "preset"


class PresetManager:
    """Manages serialization, directory indexing, and header matching for presets."""

    def save_preset(
        self,
        preset: TableMappingPreset,
        directory: Path,
    ) -> Path:
        """Serialize preset as canonical JSON into directory."""
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{_slugify(preset.name)}.json"
        target_file = directory / filename
        data = preset.model_dump(mode="json")
        target_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return target_file

    def load_preset(self, file_path: Path) -> TableMappingPreset:
        """Load and validate TableMappingPreset from a JSON file."""
        content = file_path.read_text(encoding="utf-8")
        data = json.loads(content)
        return TableMappingPreset.model_validate(data)

    def list_presets(self, directory: Path) -> tuple[TableMappingPreset, ...]:
        """List all valid presets found in directory."""
        if not directory.exists() or not directory.is_dir():
            return ()

        presets: list[TableMappingPreset] = []
        for file in sorted(directory.glob("*.json")):
            try:
                presets.append(self.load_preset(file))
            except Exception:
                continue
        return tuple(presets)

    def match_preset(
        self,
        headers: Sequence[str],
        presets: Sequence[TableMappingPreset],
    ) -> tuple[tuple[TableMappingPreset, float], ...]:
        """Rank presets by fraction of declared mapping columns in headers."""
        header_set = {h.strip() for h in headers}

        scored: list[tuple[TableMappingPreset, float]] = []

        for preset in presets:
            schema = preset.schema_definition
            mapped_cols: set[str] = set()

            # Collect identity columns
            ident = schema.identity
            for col in (
                ident.molecule_id_column,
                ident.molecule_name_column,
                ident.smiles_column,
                ident.inchikey_column,
                ident.source_system_column,
                ident.target_name_column,
                ident.run_name_column,
                ident.pose_id_column,
                ident.rank_column,
                ident.preparation_ph_column,
            ):
                if col:
                    mapped_cols.add(col)

            # Collect score columns
            for sc in schema.scores:
                mapped_cols.add(sc.column_name)

            if not mapped_cols:
                scored.append((preset, 0.0))
                continue

            matches = mapped_cols.intersection(header_set)
            score = len(matches) / len(mapped_cols)
            scored.append((preset, score))

        scored.sort(key=lambda item: (-item[1], item[0].name))
        return tuple(scored)


__all__ = ["PresetManager"]
