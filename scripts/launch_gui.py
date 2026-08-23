"""PyInstaller entry point for the FideliChem desktop application."""

from fidelichem.gui.application import main

if __name__ == "__main__":
    raise SystemExit(main())
