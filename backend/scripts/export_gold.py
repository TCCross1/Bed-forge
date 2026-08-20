#!/usr/bin/env python3
"""Export gold-standard BeamSpec JSON into training-data/extracted-json/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from corpus import GOLD_DIR, export_gold


def main() -> int:
    out = export_gold()
    files = sorted(p for p in Path(out).glob("*.json"))
    print(f"Wrote {len(files)} files to {GOLD_DIR}")
    for path in files:
        print(f"  {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
