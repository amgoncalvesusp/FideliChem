from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fidelichem") or "0.1.1"
except PackageNotFoundError:
    # Source checkouts run through pytest's ``pythonpath = ["src"]`` before
    # wheel metadata exists; keep CLI/version output deterministic there too.
    __version__ = "0.1.1"

__all__ = ["__version__"]
