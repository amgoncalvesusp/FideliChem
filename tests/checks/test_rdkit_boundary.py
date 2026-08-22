import ast
from pathlib import Path


def test_rdkit_imports_are_confined_to_chemistry_package() -> None:
    source_root = Path(__file__).parents[2] / "src" / "fidelichem"
    chemistry_root = source_root / "chemistry"
    violations: list[str] = []
    for path in source_root.rglob("*.py"):
        if chemistry_root in path.parents:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                if (
                    isinstance(node, ast.Call)
                    and (
                        (
                            isinstance(node.func, ast.Name)
                            and node.func.id == "import_module"
                        )
                        or (
                            isinstance(node.func, ast.Attribute)
                            and node.func.attr == "import_module"
                        )
                    )
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                    and (
                        node.args[0].value == "rdkit"
                        or node.args[0].value.startswith("rdkit.")
                    )
                ):
                    violations.append(str(path))
                continue
            if any(
                module == "rdkit" or module.startswith("rdkit.") for module in modules
            ):
                violations.append(str(path))
    assert violations == []
