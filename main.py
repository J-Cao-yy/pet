"""Backward-compatible root entry point for local development."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from betty_pet.__main__ import main


if __name__ == "__main__":
    raise SystemExit(main())

