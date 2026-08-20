import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def read_toml(relative_path: str) -> dict[str, object]:
    with (ROOT / relative_path).open("rb") as stream:
        return tomllib.load(stream)


@pytest.mark.config
def test_runtime_dependencies_remain_phase_zero_minimal() -> None:
    pyproject = read_toml("pyproject.toml")
    project = pyproject["project"]

    assert isinstance(project, dict)
    assert project["requires-python"] == ">=3.12,<3.13"
    assert project["dependencies"] == ["PySide6>=6.8,<7"]


@pytest.mark.config
def test_codex_configuration_enables_bounded_multi_agent_work() -> None:
    config = read_toml(".codex/config.toml")
    agents = config["agents"]

    assert config["features"] == {"multi_agent": True}
    assert isinstance(agents, dict)
    assert agents["max_threads"] == 6
    assert agents["max_depth"] == 1
    assert {
        "luna_explorer",
        "luna_worker",
        "luna_adapter",
        "luna_tests",
        "luna_docs",
        "terra_reviewer",
        "sol_architect",
    }.issubset(agents)


@pytest.mark.config
def test_ci_covers_phase_zero_gate_on_both_operating_systems() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    for required_text in (
        "ubuntu-latest",
        "windows-latest",
        'python-version: "3.12"',
        "uv lock --check",
        "uv run ruff check .",
        "uv run mypy src/fidelichem",
        "--cov-fail-under=80",
        "uv run pip-audit",
        "uv build",
    ):
        assert required_text in workflow
