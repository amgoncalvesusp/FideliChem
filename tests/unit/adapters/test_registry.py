"""Unit tests for AdapterRegistry and entry point discovery."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fidelichem.adapters.base import build_import_plan
from fidelichem.adapters.registry import AdapterRegistry
from fidelichem.domain.adapters import (
    DetectionReport,
    ImportBundle,
    ImportPlan,
    ValidationReport,
)
from fidelichem.domain.errors import AdapterNotFoundError


class MockAdapterA:
    adapter_id = "fidelichem.mock_a"
    adapter_version = "1.0.0"
    display_name = "Mock Adapter A"

    def probe(self, source: Path) -> DetectionReport:
        if source.name == "target_a":
            return DetectionReport(
                confidence=0.9,
                detected_format="fmt_a",
                suggested_adapter=self.adapter_id,
            )
        return DetectionReport(
            confidence=0.1,
            detected_format="fmt_a",
            suggested_adapter=self.adapter_id,
        )

    def plan(
        self, source: Path, options: Mapping[str, Any] | None = None
    ) -> ImportPlan:
        return build_import_plan(self.adapter_id, self.adapter_version, str(source), ())

    def parse(self, plan: ImportPlan) -> ImportBundle:
        return ImportBundle(plan=plan)

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        return ValidationReport(is_valid=True)


class MockAdapterB:
    adapter_id = "fidelichem.mock_b"
    adapter_version = "2.0.0"
    display_name = "Mock Adapter B"

    def probe(self, source: Path) -> DetectionReport:
        if source.name == "target_b":
            return DetectionReport(
                confidence=0.95,
                detected_format="fmt_b",
                suggested_adapter=self.adapter_id,
            )
        return DetectionReport(
            confidence=0.2,
            detected_format="fmt_b",
            suggested_adapter=self.adapter_id,
        )

    def plan(
        self, source: Path, options: Mapping[str, Any] | None = None
    ) -> ImportPlan:
        return build_import_plan(self.adapter_id, self.adapter_version, str(source), ())

    def parse(self, plan: ImportPlan) -> ImportBundle:
        return ImportBundle(plan=plan)

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        return ValidationReport(is_valid=True)


class CrashingProbeAdapter:
    adapter_id = "fidelichem.crashing"
    adapter_version = "0.0.1"
    display_name = "Crashing Adapter"

    def probe(self, source: Path) -> DetectionReport:
        raise RuntimeError("Disk read error inside probe")

    def plan(
        self, source: Path, options: Mapping[str, Any] | None = None
    ) -> ImportPlan:
        return build_import_plan(self.adapter_id, self.adapter_version, str(source), ())

    def parse(self, plan: ImportPlan) -> ImportBundle:
        return ImportBundle(plan=plan)

    def validate(self, bundle: ImportBundle) -> ValidationReport:
        return ValidationReport(is_valid=True)


def test_registry_registration_and_lookup() -> None:
    registry = AdapterRegistry()
    adapter_a = MockAdapterA()
    registry.register(adapter_a)

    assert registry.has("fidelichem.mock_a")
    assert not registry.has("fidelichem.mock_b")
    assert registry.get("fidelichem.mock_a") is adapter_a
    assert len(registry.list_adapters()) == 1


def test_registry_rejects_duplicate_registration_by_default() -> None:
    registry = AdapterRegistry()
    registry.register(MockAdapterA())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(MockAdapterA())


def test_registry_allows_override_when_specified() -> None:
    registry = AdapterRegistry()
    a1 = MockAdapterA()
    a2 = MockAdapterA()
    registry.register(a1)
    registry.register(a2, allow_override=True)
    assert registry.get("fidelichem.mock_a") is a2


def test_registry_raises_on_unknown_adapter() -> None:
    registry = AdapterRegistry()
    with pytest.raises(AdapterNotFoundError, match="fidelichem.unknown"):
        registry.get("fidelichem.unknown")


def test_registry_probe_all_ranks_by_confidence() -> None:
    registry = AdapterRegistry()
    registry.register(MockAdapterA())
    registry.register(MockAdapterB())

    reports_b = registry.probe_all(Path("target_b"))
    assert len(reports_b) == 2
    assert reports_b[0].suggested_adapter == "fidelichem.mock_b"
    assert reports_b[0].confidence == 0.95
    assert reports_b[1].suggested_adapter == "fidelichem.mock_a"
    assert reports_b[1].confidence == 0.1


def test_registry_probe_all_handles_crashing_adapter_safely() -> None:
    registry = AdapterRegistry()
    registry.register(MockAdapterA())
    registry.register(CrashingProbeAdapter())

    reports = registry.probe_all(Path("target_a"))
    assert len(reports) == 2
    assert reports[0].suggested_adapter == "fidelichem.mock_a"
    assert reports[0].confidence == 0.9
    # Crashing adapter produces safe 0.0 confidence report
    assert reports[1].suggested_adapter == "fidelichem.crashing"
    assert reports[1].confidence == 0.0
    assert any("probe failed" in w for w in reports[1].warnings)


def test_registry_entry_point_discovery() -> None:
    registry = AdapterRegistry()

    ep_mock = MagicMock()
    ep_mock.name = "mock_b"
    ep_mock.load.return_value = MockAdapterB

    with patch("importlib.metadata.entry_points", return_value=[ep_mock]):
        loaded_count = registry.discover_entry_points("fidelichem.adapters")
        assert loaded_count == 1
        assert registry.has("fidelichem.mock_b")


def test_registry_unregister() -> None:
    registry = AdapterRegistry()
    adapter = MockAdapterA()
    registry.register(adapter)
    assert registry.has("fidelichem.mock_a")

    registry.unregister("fidelichem.mock_a")
    assert not registry.has("fidelichem.mock_a")


def test_registry_rejects_invalid_adapters() -> None:
    registry = AdapterRegistry()

    class NoId:
        pass

    with pytest.raises(ValueError, match="non-blank 'adapter_id'"):
        registry.register(NoId)

    class BadAdapter:
        adapter_id = "bad"

    with pytest.raises(TypeError, match="EvidenceAdapter"):
        registry.register(BadAdapter)


def test_registry_entry_point_fallback_and_error_handling() -> None:
    registry = AdapterRegistry()

    # Case 1: TypeError on entry_points(group=...) -> fallback
    mock_ep_dict = {
        "fidelichem.adapters": [MagicMock(load=lambda: MockAdapterA, name="ep_a")]
    }

    def ep_caller(**kwargs):
        if kwargs:
            raise TypeError("unsupported")
        return mock_ep_dict

    with patch("importlib.metadata.entry_points", side_effect=ep_caller):
        assert registry.discover_entry_points("fidelichem.adapters") == 1
        assert registry.has("fidelichem.mock_a")

    # Case 2: Broken entry point failing to load
    broken_ep = MagicMock()
    broken_ep.load.side_effect = RuntimeError("Import error")
    broken_ep.name = "broken"

    with patch("importlib.metadata.entry_points", return_value=[broken_ep]):
        assert registry.discover_entry_points("fidelichem.adapters") == 0
