"""PyInstaller entry; internal fontmake dispatch happens before desktop startup."""

from mashi.desktop import main

if __name__ == "__main__":
    raise SystemExit(main())
