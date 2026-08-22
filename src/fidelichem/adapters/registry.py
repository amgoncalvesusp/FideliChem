"""Adapter discovery, registration, and multi-adapter probing."""

from __future__ import annotations

import importlib.metadata
import logging
from pathlib import Path

from fidelichem.adapters.base import EvidenceAdapter
from fidelichem.domain.adapters import DetectionReport
from fidelichem.domain.errors import AdapterNotFoundError

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """Registry managing available EvidenceAdapter instances and plugin discovery."""

    def __init__(self) -> None:
        self._adapters: dict[str, EvidenceAdapter] = {}

    def register(
        self,
        adapter_or_cls: EvidenceAdapter | type[EvidenceAdapter],
        *,
        allow_override: bool = False,
    ) -> None:
        """Register an adapter instance or class."""
        if isinstance(adapter_or_cls, type):
            adapter = adapter_or_cls()
        else:
            adapter = adapter_or_cls

        adapter_id = getattr(adapter, "adapter_id", "")
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise ValueError("Adapter must have a non-blank 'adapter_id'")

        if not isinstance(adapter, EvidenceAdapter):
            raise TypeError("Object does not satisfy EvidenceAdapter protocol")

        if adapter_id in self._adapters and not allow_override:
            raise ValueError(f"Adapter '{adapter_id}' is already registered")

        self._adapters[adapter_id] = adapter

    def unregister(self, adapter_id: str) -> None:
        """Remove an adapter from the registry."""
        self._adapters.pop(adapter_id, None)

    def has(self, adapter_id: str) -> bool:
        """Check if an adapter with the given identifier is registered."""
        return adapter_id in self._adapters

    def get(self, adapter_id: str) -> EvidenceAdapter:
        """Retrieve an adapter by ID or raise AdapterNotFoundError."""
        if adapter_id not in self._adapters:
            raise AdapterNotFoundError(
                f"Adapter '{adapter_id}' is not registered in the system"
            )
        return self._adapters[adapter_id]

    def list_adapters(self) -> tuple[EvidenceAdapter, ...]:
        """Return all registered adapters sorted by identifier."""
        return tuple(self._adapters[key] for key in sorted(self._adapters.keys()))

    def discover_entry_points(self, group: str = "fidelichem.adapters") -> int:
        """Discover and register adapters declared under a package entry point group."""
        discovered = 0
        try:
            try:
                eps = tuple(importlib.metadata.entry_points(group=group))
            except TypeError:
                entry_points = importlib.metadata.entry_points()
                if hasattr(entry_points, "select"):
                    eps = tuple(entry_points.select(group=group))
                elif isinstance(entry_points, dict):
                    eps = tuple(entry_points.get(group, ()))
                else:
                    eps = tuple(entry_points)
        except Exception:  # noqa: BLE001
            logger.warning("Failed to query entry points for group %s", group)
            return 0

        for ep in eps:
            try:
                loaded = ep.load()
                self.register(loaded, allow_override=True)
                discovered += 1
            except Exception as exc:  # noqa: BLE001
                ep_name = getattr(ep, "name", "unknown")
                logger.warning(
                    "Failed to load adapter entry point %s: %s", ep_name, exc
                )

        return discovered

    def probe_all(self, source: Path) -> tuple[DetectionReport, ...]:
        """Probe candidate source against registered adapters and rank results."""
        reports: list[DetectionReport] = []
        for adapter_id in sorted(self._adapters.keys()):
            adapter = self._adapters[adapter_id]
            try:
                report = adapter.probe(source)
                reports.append(report)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Adapter %s probe failed on %s: %s", adapter_id, source, exc
                )
                reports.append(
                    DetectionReport(
                        confidence=0.0,
                        detected_format="unknown",
                        warnings=(f"Adapter probe failed: {exc}",),
                        suggested_adapter=adapter_id,
                    )
                )

        return tuple(
            sorted(
                reports,
                key=lambda r: (-r.confidence, r.suggested_adapter),
            )
        )


__all__ = ["AdapterRegistry"]
